package dev.a2flow.management.agentcore.runtime.skill;

import java.nio.file.Files;
import java.nio.file.Path;
import java.util.List;
import java.util.Objects;
import java.util.Optional;
import java.util.regex.Pattern;

import jakarta.annotation.Resource;

import org.apache.commons.lang3.StringUtils;
import org.springframework.stereotype.Component;

import dev.a2flow.management.config.SkillFactoryConfigReader;
import dev.a2flow.management.release.ReleaseAssetType;
import dev.a2flow.management.release.ReleaseEnvironment;
import dev.a2flow.management.release.ReleaseModels.AssetReleaseState;
import dev.a2flow.management.release.ReleaseModels.EnvironmentState;
import dev.a2flow.management.release.ReleaseModels.ReleaseVersion;
import dev.a2flow.management.storage.db.repository.AssetReleaseStateRepository;

import lombok.extern.slf4j.Slf4j;

/**
 * SkillFactory 创建态挂载 Skill 正式包解析器。
 *
 * <p>该解析器以共享发布状态中的 ONLINE 环境指针为唯一事实源，再精确读取
 * {@code online/releases/{version}}，不扫描最大版本，也不读取被编辑 Skill 的
 * {@code preprod/current}。因此历史版本重发成功后，运行时会读取被重发版本，而不是目录中数字最大的版本。
 * 它向 AI Coding 工具提供可信绝对包根，版本选择和路径边界均由后端完成，模型不能自行拼接 workspace
 * 目录或指定历史版本。
 */
@Slf4j
@Component
public class SkillFactoryMountedSkillResolver {

    private static final String DIRECTORY_ONLINE = "online";
    private static final String DIRECTORY_RELEASES = "releases";
    private static final String FILE_SKILL_MARKDOWN = "SKILL.md";
    private static final Pattern SAFE_SKILL_CODE = Pattern.compile("[A-Za-z0-9][A-Za-z0-9._-]{0,127}");

    @Resource
    private SkillFactoryConfigReader skillFactoryConfigReader;

    @Resource
    private AssetReleaseStateRepository assetReleaseStateRepository;

    /**
     * 解析指定 Skill 当前实际生效的线上正式包；没有成功发布指针或入口文件时返回空。
     */
    public Optional<ResolvedSkillPackage> resolveEffectiveOnlineRelease(String bizKey, String skillCode) {
        if (StringUtils.isBlank(bizKey) || !isSafeSkillCode(skillCode)) {
            return Optional.empty();
        }
        Optional<Integer> effectiveVersion = effectiveOnlineVersion(skillCode);
        if (effectiveVersion.isEmpty()) {
            log.info("SkillFactory挂载Skill没有有效线上版本指针, bizKey={}, skillCode={}", bizKey, skillCode);
            return Optional.empty();
        }
        Path workspaceRoot = skillFactoryConfigReader.getWorkspaceRoot(bizKey).toAbsolutePath().normalize();
        Path skillRoot = workspaceRoot.resolve(skillCode).normalize();
        if (!skillRoot.startsWith(workspaceRoot) || !workspaceRoot.equals(skillRoot.getParent())) {
            log.warn("SkillFactory拒绝解析越界挂载Skill, bizKey={}, skillCode={}", bizKey, skillCode);
            return Optional.empty();
        }
        Path releasesRoot = skillRoot.resolve(DIRECTORY_ONLINE).resolve(DIRECTORY_RELEASES).normalize();
        Path packageRoot = releasesRoot.resolve(String.valueOf(effectiveVersion.get())).normalize();
        if (!packageRoot.startsWith(releasesRoot) || !Files.isRegularFile(packageRoot.resolve(FILE_SKILL_MARKDOWN))) {
            log.warn("SkillFactory挂载Skill正式包缺少入口文件, bizKey={}, skillCode={}, version={}, packageRoot={}",
                    bizKey, skillCode, effectiveVersion.get(), packageRoot);
            return Optional.empty();
        }
        log.info("SkillFactory已按共享ONLINE指针解析挂载Skill, bizKey={}, skillCode={}, version={}, packageRoot={}",
                bizKey, skillCode, effectiveVersion.get(), packageRoot);
        return Optional.of(new ResolvedSkillPackage(skillCode, effectiveVersion.get(), packageRoot));
    }

    /**
     * 从共享发布聚合中读取并校验 ONLINE 指针，禁止目录最大版本兜底。
     */
    private Optional<Integer> effectiveOnlineVersion(String skillCode) {
        AssetReleaseState state = assetReleaseStateRepository.find(ReleaseAssetType.SKILL, skillCode);
        if (state.getEnvironments() == null) {
            return Optional.empty();
        }
        EnvironmentState online = state.getEnvironments().get(ReleaseEnvironment.ONLINE.name());
        if (online == null || online.getVersion() == null || online.getVersion() <= 0) {
            return Optional.empty();
        }
        List<ReleaseVersion> versions = state.getVersions();
        ReleaseVersion matchedVersion = versions == null ? null : versions.stream()
                .filter(version -> Objects.equals(version.getVersion(), online.getVersion()))
                .filter(version -> StringUtils.equals(version.getVersionId(), online.getSourceId()))
                .findFirst()
                .orElse(null);
        if (matchedVersion == null
                || !StringUtils.equals(matchedVersion.getSourceDigest(), online.getDigest())) {
            log.warn("SkillFactory共享ONLINE指针与正式版本记录不一致, skillCode={}, version={}, sourceId={}, "
                            + "digest={}",
                    skillCode, online.getVersion(), online.getSourceId(), online.getDigest());
            return Optional.empty();
        }
        return Optional.of(online.getVersion());
    }

    private boolean isSafeSkillCode(String skillCode) {
        return StringUtils.isNotBlank(skillCode) && SAFE_SKILL_CODE.matcher(skillCode).matches();
    }

    /** 已解析的只读正式 Skill 包。 */
    public record ResolvedSkillPackage(String skillCode, int version, Path packageRoot) {
    }
}

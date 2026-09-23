package dev.a2flow.management.agentcore.runtime.skill;

import java.nio.file.Files;
import java.nio.file.Path;
import java.util.List;

import jakarta.annotation.Resource;

import org.apache.commons.collections4.CollectionUtils;
import org.apache.commons.lang3.StringUtils;
import org.springframework.stereotype.Component;

import com.google.common.collect.Lists;

import lombok.extern.slf4j.Slf4j;

/**
 * SkillFactory 本地 Skill 元数据查询器。
 *
 * <p>该类只负责把 Agent 配置里的 skillName 转成当前 ONLINE 指针对应的 Skill 元数据，供 AI Coding
 * system prompt 注入 `<available_skills>`。上游是 {@code AiCodingReActEngine}，下游只读取
 * SkillFactory 正式包目录结构；它不依赖原 agent-service 的 skill 表，也不负责 Skill 注册、
 * 发布或脚本执行。
 */
@Slf4j
@Component
public class SkillManager {

    private static final String SKILL_MARKDOWN = "SKILL.md";

    @Resource
    private SkillFactoryMountedSkillResolver mountedSkillResolver;

    /**
     * 按 Skill 名称生成当前有效线上正式包中的可用 Skill 元数据。
     */
    public List<SkillMetadata> queryEnabledSkillList(String bizKey, List<String> skillNameList) {
        if (StringUtils.isBlank(bizKey) || CollectionUtils.isEmpty(skillNameList)) {
            return Lists.newArrayList();
        }
        List<SkillMetadata> result = Lists.newArrayList();
        for (String skillName : skillNameList.stream().filter(StringUtils::isNotBlank).distinct().toList()) {
            SkillFactoryMountedSkillResolver.ResolvedSkillPackage skillPackage =
                    mountedSkillResolver.resolveEffectiveOnlineRelease(bizKey, skillName).orElse(null);
            if (skillPackage == null) {
                continue;
            }
            SkillMetadata metadata = new SkillMetadata();
            metadata.setName(skillName);
            metadata.setVersion(String.valueOf(skillPackage.version()));
            metadata.setDescription(readDescription(skillPackage.packageRoot()));
            result.add(metadata);
        }
        return result;
    }

    private String readDescription(Path skillLocation) {
        Path skillFile = skillLocation.resolve(SKILL_MARKDOWN);
        if (!Files.isRegularFile(skillFile)) {
            return StringUtils.EMPTY;
        }
        try (var lines = Files.lines(skillFile)) {
            return lines
                    .filter(line -> StringUtils.startsWithIgnoreCase(StringUtils.trim(line), "description:"))
                    .map(line -> StringUtils.substringAfter(line, ":").trim())
                    .findFirst()
                    .orElse(StringUtils.EMPTY);
        } catch (Exception e) {
            log.warn("SkillFactory读取挂载Skill描述失败, skillFile={}", skillFile, e);
            return StringUtils.EMPTY;
        }
    }
}

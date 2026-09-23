package dev.a2flow.management.a2ui.runtime;

import java.util.Objects;
import org.springframework.stereotype.Service;
import com.fasterxml.jackson.databind.json.JsonMapper;
import com.fasterxml.jackson.annotation.JsonCreator;
import com.fasterxml.jackson.annotation.JsonProperty;
import com.fasterxml.jackson.module.paramnames.ParameterNamesModule;
import dev.a2flow.management.a2ui.application.A2uiApplicationModels.A2uiApplicationBuild;
import dev.a2flow.management.a2ui.application.A2uiApplicationModels.*;
import dev.a2flow.management.a2ui.runtime.A2uiRuntimeContracts.*;
import dev.a2flow.management.release.ReleaseAssetType;
import dev.a2flow.management.release.ReleaseEnvironment;
import dev.a2flow.management.release.dependency.AssetDependencyModels.*;
import dev.a2flow.management.release.dependency.AssetDependencyType;
import dev.a2flow.management.release.dependency.EnvironmentAwareAssetResolver;
import dev.a2flow.management.storage.db.repository.AssetReleaseStateRepository;

@Service
public final class ReleaseStatePublishedApplicationProvider implements PublishedApplicationProvider {
    private final AssetReleaseStateRepository repository;
    private final EnvironmentAwareAssetResolver resolver;
    private final JsonMapper mapper = JsonMapper.builder()
            .addModule(new ParameterNamesModule(JsonCreator.Mode.PROPERTIES))
            .addMixIn(A2uiCompiledRequestMapping.class, RequestMappingConstructor.class)
            .addMixIn(A2uiCompiledMessageTemplateBinding.class, TemplateBindingConstructor.class)
            .addMixIn(A2uiCompiledSurfaceDeclaration.class, SurfaceConstructor.class).build();
    public ReleaseStatePublishedApplicationProvider(AssetReleaseStateRepository repository,
            EnvironmentAwareAssetResolver resolver) {
        this.repository = repository;
        this.resolver = resolver;
    }

    // 三个编译模型有兼容旧构造器；明确完整构造器，避免省略transform/footer字段。
    abstract static class RequestMappingConstructor {
        @JsonCreator RequestMappingConstructor(@JsonProperty("source") A2uiMappingSource source,
                @JsonProperty("sourcePath") String sourcePath, @JsonProperty("targetPath") String targetPath,
                @JsonProperty("constantValue") Object constantValue,
                @JsonProperty("transform") A2uiCompiledRequestTransform transform) { }
    }
    abstract static class TemplateBindingConstructor {
        @JsonCreator TemplateBindingConstructor(@JsonProperty("targetPath") String targetPath,
                @JsonProperty("source") A2uiResultSource source, @JsonProperty("sourcePath") String sourcePath,
                @JsonProperty("required") boolean required, @JsonProperty("constantValue") Object constantValue,
                @JsonProperty("transform") A2uiCompiledResultTransform transform) { }
    }
    abstract static class SurfaceConstructor {
        @JsonCreator SurfaceConstructor(@JsonProperty("surfaceId") String surfaceId,
                @JsonProperty("rootComponentId") String rootComponentId,
                @JsonProperty("footerComponentIds") java.util.List<String> footerComponentIds) { }
    }
    @Override
    public PublishedApplication current(String appCode, ReleaseEnvironment environment, long userId) {
        if (appCode == null || appCode.isBlank() || environment == null) {
            throw new RuntimeFailure("A2UI_REQUEST_INVALID");
        }
        var state = repository.find(ReleaseAssetType.A2UI_APPLICATION, appCode);
        // 共享解析器保留旧 PRT->ONLINE 规则；在同一聚合快照上提前阻断该路径。
        if (state == null || state.getEnvironments() == null
                || !state.getEnvironments().containsKey(environment.name())) {
            throw new RuntimeFailure("A2UI_APPLICATION_RELEASE_NOT_AVAILABLE");
        }
        var resolved = resolver.resolveFromState(new AssetDependencyReference()
                .setAssetType(AssetDependencyType.A2UI_APPLICATION).setAssetKey(appCode),
                new AssetResolutionContext().setRequestedEnvironment(environment).setUserId(userId), state);
        if (resolved.getResolvedEnvironment() != environment) {
            throw new RuntimeFailure("A2UI_ENVIRONMENT_MISMATCH");
        }
        // 共享resolver只比较指针与snapshot摘要字段；读取端另算内容摘要，不能信任两个相同的坏字段。
        if (resolved.getPayloadJson() == null
                || resolved.getPayloadJson().getBytes(java.nio.charset.StandardCharsets.UTF_8).length > 1024 * 1024
                || !Objects.equals(resolved.getDigest(), "sha256:"
                        + dev.a2flow.management.release.ReleaseDigestUtils.sha256(resolved.getPayloadJson()))) {
            throw new RuntimeFailure("A2UI_PUBLISHED_DIGEST_MISMATCH");
        }
        try {
            var build = mapper.readValue(resolved.getPayloadJson(), A2uiApplicationBuild.class);
            if (!Objects.equals(appCode, build.getAppCode())
                    || !Objects.equals(environment.name(), build.getPublicationEnvironment())
                    || build.getAppBuildId() == null || build.getAppBuildId().isBlank()) {
                throw new RuntimeFailure("A2UI_PUBLISHED_BUILD_INVALID");
            }
            return new PublishedApplication(new ReleaseIdentity(appCode, resolved.getSourceId(),
                    resolved.getDigest(), build.getAppBuildId(), environment), build);
        } catch (com.fasterxml.jackson.core.JsonProcessingException exception) {
            throw new RuntimeFailure("A2UI_PUBLISHED_BUILD_INVALID");
        }
    }
}

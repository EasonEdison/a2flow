package dev.a2flow.management.release.dependency;

import dev.a2flow.management.release.dependency.AssetDependencyModels.DependencyReleaseReport;
import dev.a2flow.management.release.dependency.AssetDependencyModels.DependencyValidationRequest;

/**
 * 递归校验资产依赖图能否在目标环境发布的共享接口。
 *
 * <p>调用方提供根资产和直接依赖；实现通过领域 Adapter 继续展开间接依赖，并返回确定性顺序、
 * 完整失败路径、环检测和深度限制结果。
 */
public interface AssetDependencyReleaseValidator {

    /** 校验完整依赖图，不执行发布、不移动环境指针。 */
    DependencyReleaseReport validate(DependencyValidationRequest request);
}

package dev.a2flow.management.release.dependency;

/**
 * 环境指针允许命中的不可变发布来源。
 *
 * <p>PRT 只能命中 Build，ONLINE 只能命中已封板 Version；该枚举用于阻止两个来源类型被
 * 数字版本或字符串 ID 误认为同一种对象。
 */
public enum ReleasedAssetSourceType {
    BUILD,
    VERSION
}

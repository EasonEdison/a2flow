package dev.a2flow.management.release;

/**
 * 资产 Adapter 对共享灰度控制面的接入策略。
 *
 * <p>公共发布服务只按照 Adapter 声明开放灰度动作，不根据 assetType 猜测。DISABLED 表示资产继续使用
 * 原有稳定指针；PERCENTAGE_AND_WHITELIST 表示支持 userId 尾号比例和白名单组合路由。
 */
public enum GrayReleasePolicy {

    DISABLED,
    PERCENTAGE_AND_WHITELIST
}

package dev.a2flow.management.release;

/**
 * 发布控制面的隔离环境。
 *
 * <p>PRT 指向不可变预发 Build，ONLINE 指向不可变正式 Version；两者分别记录，不能从对方推导。
 */
public enum ReleaseEnvironment {
    PRT,
    ONLINE
}

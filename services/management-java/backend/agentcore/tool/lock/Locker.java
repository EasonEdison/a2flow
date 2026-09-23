package dev.a2flow.management.agentcore.tool.lock;

import lombok.extern.slf4j.Slf4j;

/**
 * SkillFactory 本地会话锁句柄。
 *
 * <p>该类只负责在 try/finally 中释放 {@link RedisLockFactory} 创建的进程内锁。迁移到 sellerdata
 * 后暂不依赖原 agent-service Redis 工具类；后续如果需要跨实例锁，可替换工厂实现而不影响调用方。
 */
@Slf4j
public class Locker implements AutoCloseable {

    private final String lockKey;
    private final String lockValue;
    private final RedisLockFactory redisLockFactory;

    public Locker(String lockKey, String lockValue, RedisLockFactory redisLockFactory) {
        this.lockKey = lockKey;
        this.lockValue = lockValue;
        this.redisLockFactory = redisLockFactory;
    }

    @Override
    public void close() {
        if (redisLockFactory != null) {
            redisLockFactory.removeLockValue(lockKey, lockValue);
            log.info("SkillFactory释放本地会话锁, lockKey={}", lockKey);
        }
    }
}

package dev.a2flow.management.agentcore.tool.lock;

import java.util.Map;
import java.util.UUID;
import java.util.concurrent.ConcurrentHashMap;

import org.apache.commons.lang3.StringUtils;
import org.springframework.stereotype.Component;

import lombok.extern.slf4j.Slf4j;

/**
 * SkillFactory 本地会话锁工厂。
 *
 * <p>为保证迁移后的 AI Coding 链路先在 sellerdata 内跑通，这里使用进程内 Map 实现非重入锁。
 * 上游仍然通过 {@code getNonReentrantLock} 获取锁；后续如果 PRT 多实例需要严格互斥，只需把本类
 * 替换为 sellerdata 自己的 Redis/CAS 实现。该类不提供取消信号和公共 agent-service 锁能力。
 */
@Slf4j
@Component
public class RedisLockFactory {

    private static final Map<String, String> LOCAL_LOCKS = new ConcurrentHashMap<>();

    /**
     * 获取本地非重入锁。
     */
    public Locker getNonReentrantLock(String key, String lockValue, int timeoutMs) {
        String safeLockValue = StringUtils.defaultIfBlank(lockValue, UUID.randomUUID().toString());
        String existed = LOCAL_LOCKS.putIfAbsent(key, safeLockValue);
        if (existed != null) {
            log.warn("SkillFactory获取本地会话锁失败, lockKey={}", key);
            throw new RuntimeException("getNonReentrantLock failed, key=" + key);
        }
        log.info("SkillFactory获取本地会话锁成功, lockKey={}", key);
        return new Locker(key, safeLockValue, this);
    }

    /**
     * 释放本地锁，只有 value 一致时才删除。
     */
    public void removeLockValue(String lockKey, String lockValue) {
        if (StringUtils.isBlank(lockKey) || StringUtils.isBlank(lockValue)) {
            return;
        }
        LOCAL_LOCKS.remove(lockKey, lockValue);
    }
}

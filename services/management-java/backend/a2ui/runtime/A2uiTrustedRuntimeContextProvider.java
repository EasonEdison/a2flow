package dev.a2flow.management.a2ui.runtime;

import java.time.Clock;
import java.time.Instant;
import java.time.ZoneId;
import java.util.Collections;
import java.util.LinkedHashMap;
import java.util.Map;
import java.util.Objects;

import org.springframework.stereotype.Component;

/**
 * 生成一次 A2UI 激活可复用的可信运行时上下文。
 *
 * <p>时间只来自 A2Flow 服务器时钟，并统一按 Asia/Shanghai 计算自然日边界；本类仅输出通用运行时字段，
 * 不感知具体 Application、Capability 或业务参数名。</p>
 */
@Component
public final class A2uiTrustedRuntimeContextProvider {

    private static final ZoneId BUSINESS_ZONE = ZoneId.of("Asia/Shanghai");
    private static final String FIELD_RUNTIME = "runtime";
    private static final String FIELD_TIME = "time";
    private static final String FIELD_CURRENT_EPOCH_MILLIS = "currentEpochMillis";
    private static final String FIELD_CURRENT_DAY_START_EPOCH_MILLIS =
            "currentDayStartEpochMillis";
    private static final String FIELD_CURRENT_DAY_START_EPOCH_SECONDS =
            "currentDayStartEpochSeconds";
    private static final String FIELD_ZONE_ID = "zoneId";

    private final Clock clock;

    public A2uiTrustedRuntimeContextProvider() {
        this(Clock.systemUTC());
    }

    A2uiTrustedRuntimeContextProvider(Clock clock) {
        this.clock = Objects.requireNonNull(clock, "clock");
    }

    /** 捕获同一可信时刻并返回只读的通用运行时上下文。 */
    public Map<String, Object> capture() {
        Instant current = clock.instant();
        Instant dayStart = current.atZone(BUSINESS_ZONE)
                .toLocalDate()
                .atStartOfDay(BUSINESS_ZONE)
                .toInstant();
        Map<String, Object> time = new LinkedHashMap<>();
        time.put(FIELD_CURRENT_EPOCH_MILLIS, current.toEpochMilli());
        time.put(FIELD_CURRENT_DAY_START_EPOCH_MILLIS, dayStart.toEpochMilli());
        time.put(FIELD_CURRENT_DAY_START_EPOCH_SECONDS, dayStart.getEpochSecond());
        time.put(FIELD_ZONE_ID, BUSINESS_ZONE.getId());
        Map<String, Object> runtime = new LinkedHashMap<>();
        runtime.put(FIELD_TIME, Collections.unmodifiableMap(time));
        Map<String, Object> context = new LinkedHashMap<>();
        context.put(FIELD_RUNTIME, Collections.unmodifiableMap(runtime));
        return Collections.unmodifiableMap(context);
    }
}

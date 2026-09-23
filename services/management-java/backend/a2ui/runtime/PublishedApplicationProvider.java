package dev.a2flow.management.a2ui.runtime;

import dev.a2flow.management.a2ui.runtime.A2uiRuntimeContracts.PublishedApplication;
import dev.a2flow.management.release.ReleaseEnvironment;

/** 从已发布指针读取，不接受外部 Build、不读草稿、不跨环境。 */
public interface PublishedApplicationProvider {
    PublishedApplication current(String appCode, ReleaseEnvironment environment, long userId);
}

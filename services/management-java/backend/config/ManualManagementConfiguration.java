package dev.a2flow.management.config;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.ComponentScan;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.annotation.FilterType;
import org.springframework.context.annotation.Import;

import dev.a2flow.management.agentcore.runtime.tool.CapabilityActionExecutor;
import dev.a2flow.management.access.ManagementIdentityProvider;
import dev.a2flow.management.agentcore.runtime.tool.CapabilityActionToolProvider;
import dev.a2flow.management.capabilityrpc.RuntimeRpcConfiguration;
import dev.a2flow.management.entry.ManualManagementExecuteService;
import dev.a2flow.management.lifecycle.AuthoringDraftChangeService;
import dev.a2flow.management.lifecycle.SkillFactoryMethodDispatcher;

/**
 * Explicit manual-only composition root for an authenticated HTTP host to import.
 * Do not broad-scan dev.a2flow.management: legacy AI entry and execution packages are suspended.
 * DataSource, request-bound identity and a real RuntimeSkillPublicationPort remain mandatory;
 * this configuration supplies no placeholder or successful no-op adapters.
 */
@Configuration
@ComponentScan(basePackages = {
        "dev.a2flow.management.lifecycle", "dev.a2flow.management.release",
        "dev.a2flow.management.a2ui", "dev.a2flow.management.access",
        "dev.a2flow.management.fileguard", "dev.a2flow.management.storage"
}, excludeFilters = @ComponentScan.Filter(type = FilterType.ASSIGNABLE_TYPE,
        classes = AuthoringDraftChangeService.class))
@Import({SkillFactoryConfigReader.class, ManagementArtifactConfiguration.class,
        CapabilityActionToolProvider.class, CapabilityActionExecutor.class,
        dev.a2flow.management.agentcore.runtime.tool.CapabilityCatalogQueryService.class,
        RuntimeRpcConfiguration.class})
public class ManualManagementConfiguration {
    @Bean
    public ManualManagementExecuteService manualManagementExecuteService(SkillFactoryMethodDispatcher dispatcher,
            ManagementIdentityProvider identity) {
        return new ManualManagementExecuteService(dispatcher, identity);
    }
}

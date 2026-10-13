package dev.a2flow.management.managementagent;

import javax.sql.DataSource;
import com.fasterxml.jackson.databind.ObjectMapper;
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.annotation.Primary;
import org.springframework.core.env.Environment;
import org.springframework.transaction.PlatformTransactionManager;
import dev.a2flow.management.access.ManagementIdentityProvider;
import dev.a2flow.management.lifecycle.SkillFactoryMethodDispatcher;

/** Explicit composition only: the suspended legacy Java Agent and bean scan remain untouched. */
@Configuration
public class ManagementAgentConfiguration {
    @Bean @Primary public ManagementIdentityProvider trustedManagementIdentityProvider(
            @Qualifier("cookieSessionIdentityProvider") ManagementIdentityProvider cookie) {
        return new TrustedManagementIdentityProvider(cookie);
    }
    @Bean public ManagementAgentGrantStore managementAgentGrantStore() { return new ManagementAgentGrantStore(); }
    @Bean public ManagementCapabilityGuard managementCapabilityGuard(dev.a2flow.management.lifecycle.CapabilityActionDraftService drafts, dev.a2flow.management.release.PublishedAssetQueryService published, ObjectMapper mapper, dev.a2flow.management.capabilityrpc.GrpcTargetRegistry targets) { return new ManagementCapabilityGuard(drafts, published, mapper, targets); }
    @Bean public ManagementAuthoringContracts managementAuthoringContracts(dev.a2flow.management.lifecycle.CapabilityActionDraftService capabilities, ObjectMapper mapper) { return new ManagementAuthoringContracts(capabilities, mapper); }
    @Bean public ManagementToolCatalog managementToolCatalog(ObjectMapper mapper) { return new ManagementToolCatalog(mapper); }
    @Bean public ManagementToolReceiptStore managementToolReceiptStore(DataSource source) { return new ManagementToolReceiptStore(source); }
    @Bean(destroyMethod = "close") public ManagementAgentClient managementAgentClient(Environment environment) { return new ManagementAgentClient(environment); }
    @Bean public ManagementToolsService managementToolsService(ManagementAgentGrantStore grants, ManagementToolCatalog catalog,
            ManagementToolReceiptStore receipts, SkillFactoryMethodDispatcher dispatcher, ObjectMapper mapper,
            PlatformTransactionManager transactions, ManagementAuthoringContracts contracts, ManagementCapabilityGuard capabilityGuard) {
        return new ManagementToolsService(grants, catalog, receipts, dispatcher, mapper, transactions, contracts, capabilityGuard);
    }
}

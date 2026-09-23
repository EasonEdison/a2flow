package dev.a2flow.management.config;

import javax.sql.DataSource;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import dev.a2flow.management.storage.db.repository.PostgresArtifactRepository;

/** Uses the host's configured database; does not supply credentials or identity defaults. */
@Configuration
public class ManagementArtifactConfiguration {
    @Bean
    public PostgresArtifactRepository postgresArtifactRepository(DataSource dataSource) {
        return new PostgresArtifactRepository(dataSource);
    }
}

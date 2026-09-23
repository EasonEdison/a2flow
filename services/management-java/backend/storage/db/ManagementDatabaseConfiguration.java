package dev.a2flow.management.storage.db;

import javax.sql.DataSource;

import com.baomidou.mybatisplus.core.MybatisConfiguration;
import com.baomidou.mybatisplus.extension.spring.MybatisSqlSessionFactoryBean;
import com.fasterxml.jackson.databind.ObjectMapper;
import com.zaxxer.hikari.HikariConfig;
import com.zaxxer.hikari.HikariDataSource;
import org.apache.ibatis.session.SqlSessionFactory;
import org.mybatis.spring.SqlSessionTemplate;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.env.Environment;
import org.springframework.jdbc.datasource.DataSourceTransactionManager;
import org.springframework.transaction.PlatformTransactionManager;
import org.springframework.transaction.annotation.EnableTransactionManagement;

import dev.a2flow.management.support.JsonSupport;

/** 管理端共用数据源；不自动建表，也不读取工作区或 Agent 的配置。 */
@Configuration
@EnableTransactionManagement(proxyTargetClass = true)
public class ManagementDatabaseConfiguration {
    @Bean(destroyMethod = "close")
    public HikariDataSource dataSource(Environment environment) {
        String url = required(environment, "A2FLOW_MANAGEMENT_JDBC_URL");
        if (!url.startsWith("jdbc:postgresql:")) {
            throw new IllegalArgumentException("A2FLOW_MANAGEMENT_JDBC_URL must use PostgreSQL");
        }
        int size = environment.getProperty("A2FLOW_MANAGEMENT_DB_POOL_SIZE", Integer.class, 4);
        if (size < 1 || size > 32) {
            throw new IllegalArgumentException("A2FLOW_MANAGEMENT_DB_POOL_SIZE must be between 1 and 32");
        }
        HikariConfig config = new HikariConfig();
        config.setJdbcUrl(url);
        config.setUsername(required(environment, "A2FLOW_MANAGEMENT_DB_USER"));
        config.setPassword(required(environment, "A2FLOW_MANAGEMENT_DB_PASSWORD"));
        config.setMaximumPoolSize(size);
        config.setMinimumIdle(0);
        config.setConnectionTimeout(10_000);
        config.setPoolName("a2flow-management");
        return new HikariDataSource(config);
    }

    @Bean
    public ObjectMapper objectMapper() {
        return JsonSupport.mapper().copy();
    }

    @Bean
    public SqlSessionFactory sqlSessionFactory(DataSource dataSource) throws Exception {
        MybatisConfiguration configuration = new MybatisConfiguration();
        configuration.setMapUnderscoreToCamelCase(true);
        MybatisSqlSessionFactoryBean factory = new MybatisSqlSessionFactoryBean();
        factory.setDataSource(dataSource);
        factory.setConfiguration(configuration);
        factory.setMapperLocations(new org.springframework.core.io.support.PathMatchingResourcePatternResolver()
                .getResources("classpath*:storage/db/mapper/*.xml"));
        return factory.getObject();
    }

    @Bean
    public SqlSessionTemplate sqlSessionTemplate(SqlSessionFactory factory) {
        return new SqlSessionTemplate(factory);
    }

    @Bean
    public PlatformTransactionManager transactionManager(DataSource dataSource) {
        return new DataSourceTransactionManager(dataSource);
    }

    private static String required(Environment environment, String key) {
        String value = environment.getProperty(key);
        if (value == null || value.isBlank()) {
            throw new IllegalStateException("Missing required configuration: " + key);
        }
        return value;
    }
}

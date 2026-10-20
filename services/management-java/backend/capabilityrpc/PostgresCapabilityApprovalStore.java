package dev.a2flow.management.capabilityrpc;

import java.sql.SQLException;
import javax.sql.DataSource;
import org.springframework.stereotype.Component;
import dev.a2flow.management.capabilityrpc.proto.ApprovalReceipt;

/** Independent committed claim before RPC. Never joins a caller's rollbackable business transaction. */
@Component
public final class PostgresCapabilityApprovalStore implements CapabilityApprovalStore {
    private final DataSource dataSource;
    public PostgresCapabilityApprovalStore(DataSource dataSource) { this.dataSource = dataSource; }
    @Override public boolean consume(ApprovalReceipt receipt) {
        try (var connection = dataSource.getConnection()) {
            // A fresh datasource connection is required: an ambient transaction cannot authorize dispatch.
            if (!connection.getAutoCommit()) throw new SQLException("Independent autocommit connection required");
            try (var statement = connection.prepareStatement("INSERT INTO capability_approval_consumption "
                    + "(receipt_id,user_id,environment,run_id,tool_call_id,action_code,source_id,source_digest,"
                    + "arguments_digest,confirmation_id,side_effect_level,approval_policy) "
                    + "VALUES (?,?,?,?,?,?,?,?,?,?,?,?) ON CONFLICT DO NOTHING")) {
                statement.setQueryTimeout(10);
                statement.setString(1, receipt.getReceiptId()); statement.setLong(2, receipt.getUserId());
                statement.setString(3, receipt.getEnvironment().name()); statement.setString(4, receipt.getRunId());
                statement.setString(5, receipt.getToolCallId()); statement.setString(6, receipt.getActionCode());
                statement.setString(7, receipt.getSourceId()); statement.setString(8, receipt.getSourceDigest());
                statement.setString(9, receipt.getArgumentsDigest()); statement.setString(10, receipt.getConfirmationId());
                statement.setString(11, receipt.getSideEffectLevel()); statement.setString(12, receipt.getApprovalPolicy());
                return statement.executeUpdate() == 1;
            }
        } catch (SQLException unavailable) {
            // Do not expose datasource details, parameters or the receipt in public errors/logs.
            throw new IllegalStateException("Capability approval consumption unavailable");
        }
    }
}

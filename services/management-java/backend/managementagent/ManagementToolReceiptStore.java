package dev.a2flow.management.managementagent;

import javax.sql.DataSource;
import com.google.protobuf.ByteString;
import org.springframework.jdbc.core.JdbcTemplate;
import dev.a2flow.management.managementagent.proto.ExecuteToolRequest;
import dev.a2flow.management.managementagent.proto.ToolResult;

/** Receipt identity includes both trusted owner and conversation; caller IDs cannot select another owner. */
public final class ManagementToolReceiptStore {
    private final JdbcTemplate jdbc;
    public ManagementToolReceiptStore(DataSource source) { jdbc = new JdbcTemplate(source); }
    public boolean claim(ManagementAgentGrantStore.Grant grant, ExecuteToolRequest request, String digest) {
        long now = System.currentTimeMillis();
        return jdbc.update("INSERT INTO management_agent_tool_receipt "
                + "(namespace,user_id,conversation_id,request_id,parent_request_id,turn_id,tool_call_id,method,arguments_digest,status,created_at,updated_at) "
                + "VALUES (?,?,?,?,?,?,?,?,?,'CLAIMED',?,?) ON CONFLICT DO NOTHING",
                grant.namespace(), grant.userId(), request.getConversationId(), request.getRequestId(),
                grant.parentRequestId(), request.getTurnId(), request.getToolCallId(), request.getName(), digest, now, now) == 1;
    }
    public Receipt read(ManagementAgentGrantStore.Grant grant, String requestId) {
        var rows = jdbc.query("SELECT arguments_digest,status,error_code,result_json::text FROM management_agent_tool_receipt "
                        + "WHERE namespace=? AND user_id=? AND conversation_id=? AND request_id=?",
                (row, index) -> new Receipt(row.getString(1), ToolResult.newBuilder()
                        .setRequestId(requestId).setStatus(row.getString(2)).setErrorCode(row.getString(3))
                        .setResultJson(ByteString.copyFromUtf8(row.getString(4) == null ? "{}" : row.getString(4))).build()),
                grant.namespace(), grant.userId(), grant.conversationId(), requestId);
        return rows.isEmpty() ? null : rows.get(0);
    }
    public void complete(ManagementAgentGrantStore.Grant grant, ToolResult result) {
        int changed = jdbc.update("UPDATE management_agent_tool_receipt SET status=?,error_code=?,result_json=?::jsonb,updated_at=? "
                        + "WHERE namespace=? AND user_id=? AND conversation_id=? AND request_id=? AND status='CLAIMED'",
                result.getStatus(), result.getErrorCode(), result.getResultJson().toStringUtf8(), System.currentTimeMillis(),
                grant.namespace(), grant.userId(), grant.conversationId(), result.getRequestId());
        if (changed != 1) throw new IllegalStateException("MANAGEMENT_TOOL_RECEIPT_CONFLICT");
    }
    public record Receipt(String digest, ToolResult result) { }
}

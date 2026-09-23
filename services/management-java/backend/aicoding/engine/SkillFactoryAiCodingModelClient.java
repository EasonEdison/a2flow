package dev.a2flow.management.aicoding.engine;

import java.util.List;
import org.springframework.ai.chat.messages.Message;
import org.springframework.ai.chat.model.ChatResponse;
import org.springframework.ai.tool.ToolCallback;
import reactor.core.publisher.Flux;
import dev.a2flow.management.agentcore.infrastructrue.kconf.model.LLMModelConfig;

/** Port declaration only. A real Runtime adapter is required; no model provider is selected here. */
public interface SkillFactoryAiCodingModelClient {
    Flux<ChatResponse> streamCall(LLMModelConfig configuration, List<Message> messages, List<ToolCallback> tools);
}

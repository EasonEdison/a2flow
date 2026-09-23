package dev.a2flow.management.a2ui.application;

/**
 * 不可变 Application Build ID 生成端口。
 *
 * <p>领域 compiler 只传入 sourceDigest；生产实现可接受控 ID 服务，测试使用确定性 fake。本端口不
 * 负责发布、数据库或以客户端输入覆盖 Build identity。
 */
@FunctionalInterface
public interface A2uiBuildIdGenerator {

    /** 根据已完成的 sourceDigest 生成稳定、非空 Build ID。 */
    String generate(String sourceDigest);
}

package dev.a2flow.management.capabilityrpc;

import java.io.File;
import java.net.InetSocketAddress;
import java.util.List;
import io.grpc.BindableService;
import io.grpc.Server;
import io.grpc.netty.shaded.io.grpc.netty.GrpcSslContexts;
import io.grpc.netty.shaded.io.grpc.netty.NettyServerBuilder;
import io.grpc.netty.shaded.io.netty.handler.ssl.ClientAuth;

/** First hop: loopback-only explicit local mode, otherwise engine-specific trusted CA with mandatory mTLS. */
public final class TrustedGrpcServer {
    private TrustedGrpcServer() { }
    public static Server start(String host, int port, boolean loopbackPlaintext, String cert, String key,
            String engineTrustCa, List<BindableService> services) throws Exception {
        if (port < 0 || port > 65535 || services.isEmpty()) throw new IllegalArgumentException("Invalid gRPC listener");
        var builder = NettyServerBuilder.forAddress(new InetSocketAddress(host, port)).maxInboundMessageSize(2 * 1024 * 1024);
        if (loopbackPlaintext) {
            if (!"127.0.0.1".equals(host)) throw new IllegalArgumentException("Local RPC may only bind IPv4 loopback");
        } else {
            if (cert == null || key == null || engineTrustCa == null) throw new IllegalArgumentException("Engine mTLS credentials required");
            builder.sslContext(GrpcSslContexts.forServer(new File(cert), new File(key))
                    .trustManager(new File(engineTrustCa)).clientAuth(ClientAuth.REQUIRE).build());
        }
        services.forEach(builder::addService);
        return builder.build().start();
    }
}

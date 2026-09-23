package dev.a2flow.management.authoring.session.model;

import lombok.Data;
import lombok.experimental.Accessors;

/**
 * Authoring Chat 新建会话结果。
 *
 * <p>创建命令只返回新激活的 sessionId，历史列表继续由独立查询接口负责。
 */
@Data
@Accessors(chain = true)
public class AuthoringSessionCreateResult {

    private String sessionId;
}

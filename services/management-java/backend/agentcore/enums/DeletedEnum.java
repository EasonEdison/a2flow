package dev.a2flow.management.agentcore.enums;

import lombok.AllArgsConstructor;
import lombok.Getter;

/**
 * 删除状态枚举

 * @date 2026/4/27
 */
@Getter
@AllArgsConstructor
public enum DeletedEnum {

    /**
     * 有效
     */
    VALID(0, "有效"),

    /**
     * 已删除
     */
    DELETED(1, "已删除");

    private final Integer code;
    private final String desc;

    public static DeletedEnum getByCode(Integer code) {
        if (code == null) {
            return null;
        }
        for (DeletedEnum e : values()) {
            if (e.getCode().equals(code)) {
                return e;
            }
        }
        return null;
    }
}

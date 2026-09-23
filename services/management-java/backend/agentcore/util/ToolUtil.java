package dev.a2flow.management.agentcore.util;

import org.apache.commons.lang3.StringUtils;
import org.apache.commons.lang3.math.NumberUtils;

import dev.a2flow.management.support.DeploymentEnvironment;

/**

 * Created on 2026-05-03
 */
public class ToolUtil {
    public static String getEnvName() {
        return DeploymentEnvironment.name();
    }

    public static long convertLongDefault0(String number) {
        try {
            if (!StringUtils.isNumeric(number)) {
                return 0;
            }
            return NumberUtils.toLong(number, 0);
        } catch (Exception e) {
            return 0;
        }
    }
}

package dev.a2flow.management.release.diff;

import lombok.Data;
import lombok.experimental.Accessors;

/**
 * 领域层交给共享 Diff 引擎的单个文件资源。
 *
 * <p>Skill lifecycle 负责在受控 workspace 边界内读取文件并生成本模型；组件和业务能力 Adapter
 * 负责生成虚拟 JSON 文件。共享引擎不访问 workspace、数据库或对象存储。BINARY 资源不得携带
 * content，TEXT/JSON content 必须是已经按 UTF-8 解码的字符串。
 */
@Data
@Accessors(chain = true)
public class ReleaseDiffResource {

    private String path;
    private String oldPath;
    private ReleaseDiffContentType contentType;
    private String language;
    private String digest;
    private Long size;
    private String content;
}

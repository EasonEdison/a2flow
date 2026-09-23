package dev.a2flow.management.protobuf;

import java.util.ArrayList;
import java.util.List;
import lombok.Data;

/** Typed knowledge query parameters retained at the Runtime boundary. */
@Data
public class RecallKnowledgeParam {
    private String globalQuery;
    private List<KnowledgeParam> knowledgeParam = new ArrayList<>();
    @Data
    public static class KnowledgeParam {
        private String exclusiveQuery;
        private String userId;
        private String bizCode;
        private String baseId;
        private List<String> itemIdList = new ArrayList<>();
        private int maxResults;
        private float threshold;
        private List<TagFilterParam> tagFilter = new ArrayList<>();
        private List<CategoryFilterParam> categoryFilter = new ArrayList<>();
        private boolean searchConfig;
        private List<Integer> searchChannel = new ArrayList<>();
    }
    @Data
    public static class TagFilterParam {
        private String tagName;
        private List<String> tagValue = new ArrayList<>();
    }
    @Data
    public static class CategoryFilterParam {
        private String categoryName;
        private java.math.BigInteger categoryId;
    }
}

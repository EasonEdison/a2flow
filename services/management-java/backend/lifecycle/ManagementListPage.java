package dev.a2flow.management.lifecycle;

import java.util.List;

/** 统一的编号分页响应，total 是筛选后的总数而不是本页条数。 */
public record ManagementListPage<T>(List<T> list, long total, int page, int pageSize) { }

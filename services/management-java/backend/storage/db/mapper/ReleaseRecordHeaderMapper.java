package dev.a2flow.management.storage.db.mapper;

import java.util.List;

import org.apache.ibatis.annotations.Mapper;
import org.apache.ibatis.annotations.Param;

import dev.a2flow.management.storage.db.entity.ReleaseRecordHeader;

@Mapper
public interface ReleaseRecordHeaderMapper {
    List<ReleaseRecordHeader> selectHeaders(@Param("recordRefs") List<String> recordRefs);
}

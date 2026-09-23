import React from 'react';
import { Button, Input, Select, Typography } from 'antd';
import { DeleteOutlined, PlusOutlined } from '@ant-design/icons';
import type { CapabilityActionValueSchema, CapabilityActionValueSchemaType } from './api';

const { Text } = Typography;

const primitiveTypeOptions = [
  { value: 'string', label: '字符' },
  { value: 'integer', label: '整数' },
  { value: 'number', label: '数字（允许小数）' },
  { value: 'boolean', label: '布尔' },
];

const schemaTypeOptions = [
  ...primitiveTypeOptions,
  { value: 'object', label: '对象' },
  { value: 'array', label: '数组' },
];

type CapabilityInputSchemaEditorProps = {
  value?: CapabilityActionValueSchema;
  onChange: (value: CapabilityActionValueSchema) => void;
};

function schemaForType(type: CapabilityActionValueSchemaType): CapabilityActionValueSchema {
  if (type === 'array') return { type, items: { type: 'string' } };
  if (type === 'object') return { type, properties: {} };
  return { type };
}

const ValueSchemaEditor: React.FC<{
  value: CapabilityActionValueSchema;
  onChange: (value: CapabilityActionValueSchema) => void;
  depth: number;
}> = ({ value, onChange, depth }) => {
  const type = value.type || 'string';
  const properties = Object.entries(value.properties || {});

  const updateProperty = (
    index: number,
    name: string,
    schema: CapabilityActionValueSchema,
    required: boolean,
  ) => {
    const nextProperties: Record<string, CapabilityActionValueSchema> = {};
    const nextRequired: string[] = [];
    properties.forEach(([currentName, currentSchema], currentIndex) => {
      const propertyName = currentIndex === index ? name : currentName;
      if (!propertyName.trim()) return;
      nextProperties[propertyName] = currentIndex === index ? schema : currentSchema;
      const isRequired =
        currentIndex === index ? required : (value.required || []).includes(currentName);
      if (isRequired) nextRequired.push(propertyName);
    });
    onChange({
      type: 'object',
      properties: nextProperties,
      ...(nextRequired.length ? { required: nextRequired } : {}),
    });
  };

  return (
    <div className="capability-schema-node">
      <label>
        元素类型
        <Select
          value={type}
          options={depth >= 7 ? primitiveTypeOptions : schemaTypeOptions}
          onChange={(nextType) =>
            onChange(schemaForType(nextType as CapabilityActionValueSchemaType))
          }
        />
      </label>
      {type === 'array' ? (
        <div className="capability-schema-nested">
          <Text strong>子数组元素</Text>
          <ValueSchemaEditor
            value={value.items || { type: 'string' }}
            onChange={(items) => onChange({ type: 'array', items })}
            depth={depth + 1}
          />
        </div>
      ) : null}
      {type === 'object' ? (
        <div className="capability-schema-properties">
          <div className="capability-section-title">
            <div>
              <Text strong>对象属性</Text>
              <Text type="secondary">逐项描述数组元素对象；属性也可以继续嵌套对象或数组。</Text>
            </div>
            <Button
              size="small"
              icon={<PlusOutlined />}
              onClick={() => {
                const propertyName = `field${properties.length + 1}`;
                onChange({
                  type: 'object',
                  properties: { ...(value.properties || {}), [propertyName]: { type: 'string' } },
                  ...(value.required?.length ? { required: value.required } : {}),
                });
              }}
            >
              添加属性
            </Button>
          </div>
          {properties.map(([name, schema], index) => {
            const required = (value.required || []).includes(name);
            return (
              <div className="capability-schema-property" key={`${index}-${name}`}>
                <div className="capability-schema-property-row">
                  <Input
                    value={name}
                    placeholder="属性名"
                    onChange={(event) =>
                      updateProperty(index, event.target.value, schema, required)
                    }
                  />
                  <Select
                    value={schema.type || 'string'}
                    options={depth >= 7 ? primitiveTypeOptions : schemaTypeOptions}
                    onChange={(nextType) =>
                      updateProperty(
                        index,
                        name,
                        schemaForType(nextType as CapabilityActionValueSchemaType),
                        required,
                      )
                    }
                  />
                  <Select
                    value={required ? 'true' : 'false'}
                    options={[
                      { value: 'true', label: '必填' },
                      { value: 'false', label: '选填' },
                    ]}
                    onChange={(nextRequired) =>
                      updateProperty(index, name, schema, nextRequired === 'true')
                    }
                  />
                  <Button
                    icon={<DeleteOutlined />}
                    aria-label={`删除属性${name}`}
                    onClick={() => {
                      const nextProperties = { ...(value.properties || {}) };
                      delete nextProperties[name];
                      const nextRequired = (value.required || []).filter((item) => item !== name);
                      onChange({
                        type: 'object',
                        properties: nextProperties,
                        ...(nextRequired.length ? { required: nextRequired } : {}),
                      });
                    }}
                  />
                </div>
                {schema.type === 'array' || schema.type === 'object' ? (
                  <div className="capability-schema-nested">
                    <ValueSchemaEditor
                      value={schema}
                      onChange={(nextSchema) => updateProperty(index, name, nextSchema, required)}
                      depth={depth + 1}
                    />
                  </div>
                ) : null}
              </div>
            );
          })}
          {!properties.length ? (
            <Text type="secondary">暂无属性，请添加数组元素对象的字段。</Text>
          ) : null}
        </div>
      ) : null}
    </div>
  );
};

const CapabilityInputSchemaEditor: React.FC<CapabilityInputSchemaEditorProps> = ({
  value,
  onChange,
}) => (
  <div className="capability-schema-editor capability-form-field-wide">
    <div className="capability-section-title">
      <div>
        <Text strong>数组元素结构</Text>
        <Text type="secondary">
          数组作为一个完整 JSON 值传入；这里定义 items，可递归描述对象属性和子数组。
        </Text>
      </div>
    </div>
    <ValueSchemaEditor value={value || { type: 'string' }} onChange={onChange} depth={0} />
  </div>
);

export default CapabilityInputSchemaEditor;

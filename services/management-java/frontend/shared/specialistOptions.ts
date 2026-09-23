import type { SkillFactorySpecialistOption } from '../api';

export const defaultSkillFactorySpecialists: SkillFactorySpecialistOption[] = [
  { id: '100001', name: '直播专员', roleCode: 'live_specialist' },
  { id: '100002', name: '内容专员', roleCode: 'content_specialist' },
  { id: '100003', name: '保障专员', roleCode: 'guarantee_specialist' },
];

export const specialistOptionId = (option?: SkillFactorySpecialistOption | null): string =>
  String(
    option?.id || option?.digitalEmployeeId || option?.specialistId || option?.value || '',
  ).trim();

export const specialistOptionName = (option?: SkillFactorySpecialistOption | null): string =>
  String(option?.name || option?.specialistName || option?.label || '').trim();

export const normalizeSkillFactorySpecialists = (
  specialists?: SkillFactorySpecialistOption[] | null,
): SkillFactorySpecialistOption[] =>
  (specialists || [])
    .map((item) => {
      const id = specialistOptionId(item);
      const name = specialistOptionName(item);
      return { ...item, id, name };
    })
    .filter((item) => item.id && item.name);

export const resolveSkillFactorySpecialists = (
  specialists?: SkillFactorySpecialistOption[] | null,
): SkillFactorySpecialistOption[] => {
  const normalized = normalizeSkillFactorySpecialists(specialists);
  return normalized.length ? normalized : defaultSkillFactorySpecialists;
};

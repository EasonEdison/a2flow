package dev.a2flow.management.a2ui.catalog;

import java.lang.reflect.Field;
import java.lang.reflect.InvocationTargetException;
import java.lang.reflect.Method;
import java.util.List;
import java.util.Map;

import dev.a2flow.management.a2ui.application.A2uiApplicationManifestCompilerService;
import dev.a2flow.management.a2ui.catalog
        .A2uiOfficialBasicCatalogImporter.OfficialBasicCatalogSnapshot;
import dev.a2flow.management.a2ui.registry.A2uiComponentOriginType;
import dev.a2flow.management.a2ui.registry.A2uiRegistryValidationException;
import dev.a2flow.management.access.AssetAuthorizationService;
import dev.a2flow.management.lifecycle.domain.ComponentAsset;
import dev.a2flow.management.release.A2uiCatalogReleaseAssetAdapter;
import dev.a2flow.management.release.ReleaseModels.AssetSnapshot;
import dev.a2flow.management.storage.db.repository.SkillFactoryComponentAssetRepository;
import dev.a2flow.management.storage.db.repository
        .SkillFactoryComponentAssetRepository.ComponentAssetQuery;
import dev.a2flow.management.support.JsonSupport;

/** 不访问数据库，验证管理员固定入口只导入内置 Official 锁定快照。 */
public final class A2uiOfficialCatalogImportTest {
    private A2uiOfficialCatalogImportTest() { }

    public static void main(String[] args) throws Exception {
        A2uiOfficialBasicCatalogImporter importer = new A2uiOfficialBasicCatalogImporter();
        OfficialBasicCatalogSnapshot snapshot = importer.loadLockedSnapshot("admin");
        if (snapshot.getAtomAssets().size() != 18) {
            throw new AssertionError("official atom count changed");
        }
        for (ComponentAsset atom : snapshot.getAtomAssets()) {
            if (!A2uiComponentOriginType.A2UI_OFFICIAL.name().equals(
                    atom.getA2uiContract().get("componentOriginType"))) {
                throw new AssertionError("official atom origin lost");
            }
        }

        A2uiCatalogRegistryService service = new A2uiCatalogRegistryService();
        set(service, "assetAuthorizationService", authorization(true));
        set(service, "officialBasicCatalogImporter", importer);
        set(service, "catalogImportTransactionService", new A2uiCatalogImportTransactionService() {
            @Override
            public ComponentAsset importOfficialSnapshot(
                    OfficialBasicCatalogSnapshot value, String operator) {
                if (value == null || value.getAtomAssets().size() != 18
                        || !A2uiOfficialBasicCatalogImporter.CATALOG_ID.equals(
                        value.getCatalogAsset().getComponentName())
                        || !"admin".equals(operator)) {
                    throw new AssertionError("untrusted official snapshot");
                }
                return value.getCatalogAsset();
            }
        });
        Map<String, Object> result = service.importOfficial("admin");
        if (!A2uiCatalogSourceType.A2UI_OFFICIAL.name().equals(result.get("catalogSourceType"))
                || !Integer.valueOf(18).equals(result.get("importedAtomCount"))
                || !A2uiOfficialBasicCatalogImporter.SOURCE_COMMIT.equals(
                result.get("sourceCommit"))) {
            throw new AssertionError("official import projection invalid");
        }

        set(service, "assetAuthorizationService", authorization(false));
        try {
            service.importOfficial("user");
            throw new AssertionError("non-admin imported official catalog");
        } catch (A2uiRegistryValidationException expected) { }
        verifyOfficialAtomCanBeFrozen(snapshot);
        System.out.println("PASS: admin-only locked Google A2UI Official Basic Catalog import");
    }

    private static void verifyOfficialAtomCanBeFrozen(
            OfficialBasicCatalogSnapshot snapshot) throws Exception {
        ComponentAsset officialText = snapshot.getAtomAssets().stream()
                .filter(atom -> "Text".equals(atom.getComponentName())).findFirst().orElseThrow();
        ComponentAsset catalog = new ComponentAsset()
                .setAssetType("A2UI_CATALOG")
                .setComponentName("reading.test.catalog")
                .setRuntimeConfigJson(JsonSupport.toJSON(Map.of(
                        "catalogId", "reading.test.catalog",
                        "protocolVersion", "v0.9.1",
                        "catalogSourceType", "PLATFORM_MANAGED",
                        "componentCodes", List.of("Text"))))
                .setEnabled(Boolean.TRUE);
        A2uiCatalogReleaseAssetAdapter adapter = new A2uiCatalogReleaseAssetAdapter();
        set(adapter, "assetRepository", new SkillFactoryComponentAssetRepository() {
            @Override
            public ComponentAsset findByAssetTypeAndName(String assetType, String componentName) {
                return catalog;
            }

            @Override
            public List<ComponentAsset> list(ComponentAssetQuery query, boolean enabledOnly) {
                return List.of(officialText);
            }
        });
        AssetSnapshot frozen = adapter.currentSnapshot("reading.test.catalog", Map.of());
        if (frozen == null || !frozen.getPayloadJson().contains("A2UI_OFFICIAL")) {
            throw new AssertionError("official atom origin was not frozen into catalog");
        }
        verifyOfficialAtomCanBeCompiled(frozen);
    }

    @SuppressWarnings("unchecked")
    private static void verifyOfficialAtomCanBeCompiled(AssetSnapshot frozen) throws Exception {
        Map<String, Object> payload = JsonSupport.fromJSON(frozen.getPayloadJson(), Map.class);
        Method catalogComponents = A2uiApplicationManifestCompilerService.class.getDeclaredMethod(
                "catalogComponents", String.class, Map.class, String.class, String.class);
        catalogComponents.setAccessible(true);
        Object compiled = catalogComponents.invoke(new A2uiApplicationManifestCompilerService(),
                "reading.test.catalog", payload, "1", frozen.getDigest());
        if (!(compiled instanceof List<?>) || ((List<?>) compiled).size() != 1) {
            throw new AssertionError("official atom was not accepted by manifest compiler");
        }
        List<Map<String, Object>> components =
                (List<Map<String, Object>>) payload.get("components");
        ((Map<String, Object>) components.get(0).get("contract"))
                .put("componentOriginType", "UNTRUSTED");
        try {
            catalogComponents.invoke(new A2uiApplicationManifestCompilerService(),
                    "reading.test.catalog", payload, "1", frozen.getDigest());
            throw new AssertionError("untrusted atom origin was accepted");
        } catch (InvocationTargetException expected) {
            if (!(expected.getCause() instanceof RuntimeException)) {
                throw expected;
            }
        }
    }

    private static AssetAuthorizationService authorization(boolean admin) {
        return new AssetAuthorizationService() {
            @Override
            public boolean isAdmin(String operator) {
                return admin && "admin".equals(operator);
            }
        };
    }

    private static void set(Object target, String name, Object value) throws Exception {
        Field field = target.getClass().getDeclaredField(name);
        field.setAccessible(true);
        field.set(target, value);
    }
}

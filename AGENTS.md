# AGENTS

## Быстрый индекс
- `README.adoc` — короткое описание репозитория.
- `00-meta/layers/` — канонический source of truth по каждому слою.
- `00-meta/layers-summary/` — cross-layer tables, группы и агрегированные summaries.
- `00-meta/governance/` — release, workflow, adoption и user-readable operating rules.
- `00-meta/governance/PRODUCT-METAMODEL-ANALYSIS-WORKFLOW-001.adoc` — человекочитаемый регламент совместной работы Аналитика и AI агента от входного сигнала до approval-ready product metamodel.
- `00-meta/governance/PRODUCT-CHANGE-EXECUTION-WORKFLOW-001.adoc` — человекочитаемый регламент совместной работы Аналитика и AI агента от approved wave до implementation, verification и release/deploy boundary.
- `00-meta/governance/ANTORA-PUBLICATION-VIEW-RULES-001.adoc` — канонические правила publication view, Summary entry points и audience-oriented navigation в Antora.
- `00-meta/repository-structure/` — правила дерева, доменов и canonical paths.
- `00-meta/schemas/` и `00-meta/templates/` — базовый card contract.
- `00-meta/validate_model.py` — validator модели и hash snapshots.
- `domains/<domain>/.summary/` — локальный meta/context домена внутри канона.

## Что Это За Репо
- Это reference-model repo, а не приложение: здесь нет product runtime, build или package-manager workflow.
- Root `00-meta/` и root `AGENTS.md` вместе образуют governance package эталона.
- Канонический формат документов репозитория — `.adoc` для прямого использования в Antora; `AGENTS.md` сохранен как единственный compatibility shim для agent instructions.
- Product repos должны копировать у принятого release не только root `00-meta/`, но и root `AGENTS.md`, потому что этот файл тоже задает repository-wide operating rules.
- Root `00-meta/` остается единственным source of truth для governance, schemas, naming, templates, traceability и canonical layer set.

## Сначала Прочитай
- Сначала `README.adoc`, затем этот `AGENTS.md`.
- Для структуры: `00-meta/repository-structure/ROOT-TREE-000.adoc`, `LAYER-STRUCTURE-RULES-001.adoc`, `DOMAIN-DECOMPOSITION-RULES-001.adoc`.
- Для layer-specific работы приоритет у `00-meta/layers/*.adoc`; `00-meta/layers-summary/` используй только как обзор. При конфликте побеждает `layers/`.

## Структура Репо
- Канонические пути слоев заданы в `00-meta/layers-summary/LAYER-CANONICAL-TABLES-002.adoc`; локальные вариации path names запрещены.
- Домен может только пометить слой как `unused`; нельзя добавлять, удалять, переименовывать или переопределять канонические слои локально.
- Domain-local `.summary/` хранит только локальный meta/context и не заменяет root governance.
- Единственный допустимый root-level service layer для Antora — `Antora/`; он не меняет канон дерева и не подменяет `00-meta/`, `common/` или `domains/`.
- Domain-local `.summary/` может materialize как Summary entry point в Antora publication view, но не заменяет полный канонический стек домена.
- Audience-oriented блоки Antora группируют domain content только для reading flow; канон слоев и canonical paths остаются без изменений.
- Каждый домен должен иметь собственного ответственного, зафиксированного в `MAP-*` через базовое поле `owner`.
- Дочерний домен живет в `domains/<parent>/domains/<child>/`; `parent_domain` должен совпадать с фактическим путем.
- У каждого дочернего домена должны быть собственные объекты минимум в `.summary`, `08-layer-requirements`, `24-layer-knowledge-sources` и `25-layer-traceability`.

## Если Меняешь Канон
- Меняешь набор слоев, canonical names, canonical paths или semantics — обновляй `00-meta/layers/` и `00-meta/layers-summary/` в одном change set.
- Новые канонические слои добавляются только в хвост числового списка.
- Меняешь naming, schemas или structural rules — сначала root `00-meta/`, потом затронутые домены.
- Меняешь формат, service layout или Antora-инфраструктуру — обновляй root `00-meta/` и содержимое `Antora/` в одном change set, не ломая каноническую структуру доменов.
- Меняешь publication mapping Antora, Summary entry points или separation baseline/change в navigation — обновляй root `00-meta/`, `Antora/` и root `AGENTS.md` в одном change set.
- Если меняется информация о слоях или о самой модели в root `00-meta/`, синхронно обновляй `AGENTS.md`.
- Любое принятое изменение root `00-meta/` — новый release scope и требует явного release identifier по `00-meta/governance/REFERENCE-MODEL-RELEASE-POLICY-001.adoc`.

## Валидатор
- Валидатор живет в `00-meta/validate_model.py`.
- Он проверяет только model-scope: root `00-meta/` и `domains/`; прочие root-level файлы и директории в validation scope не входят.
- Валидатор проверяет структуру, naming rules, AsciiDoc/YAML cards, обязательные секции и поля, selected enums, internal refs, child-domain rules и sync layer docs с summary docs.
- Базовые hash snapshots хранятся внутри `00-meta/validate_model.py`.
- Основные команды: `python3 00-meta/validate_model.py check` и `python3 00-meta/validate_model.py update-hashes --kind all`.

## Рабочий Цикл Агента
- Сначала определи контур: `common/`, root `00-meta/`, верхнеуровневый domain, дочерний domain.
- Собери источники и построи список объектов по каноническим слоям.
- Если source basis домена — код продукта, UI-разметка или runtime behavior, не останавливайся на верхнеуровневой domain map, одном агрегированном scenario или только `CODE-*`-summary.
- Подтвержденные user routes, steps, UI states и distinct outcomes materialize в `07-layer-scenarios-ux/` как отдельные `SCN-*`.
- Новый `SCN-*` materialize в той же волне хотя бы с одним validating `TEST-*` в `20-layer-quality-testing/`; отсутствие пары до review-ready state оформляется как явный `RISK-*`.
- `TEST-*`, который проверяет user-facing route, failure, degraded или recovery behavior, обязан явно ссылаться на `SCN-*`, который он подтверждает.
- Подтвержденные object invariants, field constraints, validation, normalization и merge rules materialize в `09-layer-domain-rules/` как `RULE-*`.
- Подтвержденная структура устойчивых объектов, schema document, fields, relations и значимые state transitions materialize в `13-layer-data-architecture/` как `DATA-*`.
- `14-layer-code-implementation/` отражает реализацию, но не заменяет `07`, `09` и `13`; omission подтвержденного code-derived scope требует явной причины, source basis и linked `RISK-*`.
- Если product wave меняет actor-facing behavior и пользователь не указал изменение ценности и антиценности, агент обязан явно запросить это до formalize/implementation.
- На analysis-stage и execution-stage агент обязан явно показывать текущий шаг, основание вывода, просмотренные источники или изменяемые объекты, незакрытые gaps и следующий ожидаемый ход.
- Если продолжение требует approval, спорной трактовки semantics или behavior-changing выбора, агент обязан остановиться и запросить решение Аналитика, а не делать скрытое предположение.
- Product wave стартует в исходном домене, затем проверяет impact на root, родительские и соседние домены; подтвержденный impact запускает каскадную wave в затронутых доменах.
- Явно отмечай `unused` слои в `.summary`, если они действительно не применяются.
- Не копируй общие объекты вниз без необходимости.
- Локальные `REF-*` создавай только когда прямой ссылки на объект выше по иерархии недостаточно для локальной навигации.
- Заполняй `24-layer-knowledge-sources/` и `25-layer-traceability/` в той же волне, где появляется новый подтвержденный scope.

## Карточки
- Карточки — AsciiDoc с финальным `== Технические поля` и YAML source block.
- Ориентиры: `00-meta/templates/CARD-CREATION-RULES-001.adoc` и `00-meta/schemas/BASE-CARD-SCHEMA-001.adoc`.
- Обязательные разделы фиксированы: `Краткое описание`, `Текущее состояние`, `Что подтверждено`, `Замечания аналитика`, `Требуемые изменения`, `Решение по карточке`, `Связанные объекты`, `Источники`, `Артефакты`, `Технические поля`.
- Проза и YAML должны совпадать; обязательные отказы заполняются через `mandatory_input_status`, `refusal_reasons` и `resulting_risk_refs`.
- Имя файла: `<PREFIX>-<DOMAIN>-<NUMBER>-<slug>.adoc`; `slug` — English lowercase hyphenated.

## Качество Предметных Карточек
- Для предметных карточек приоритет у domain semantics, подтвержденной источниками, кодом, UI-текстом и артефактами, а не у формулировок change wave или structural completeness.
- Карточки `VALUE-*`, `GOAL-*`, `PROC-*`, `SCN-*`, `REQ-*`, `RULE-*`, `DATA-*`, `CODE-*`, `NFR-*`, `RISK-*`, `TEST-*`, `METRIC-*`, `SEC-*`, `ACCESS-*`, `PERF-*`, `CRIT-*` не должны превращаться в prose про текущую wave, materialization или explicit links, если предмет карточки можно описать точнее в domain language.
- Если source basis дает точные domain terms, используй их в `Краткое описание`, `Текущее состояние` и `Что подтверждено`; не подменяй `converters`, `flows`, `schema`, `import`, `export`, `properties`, `rules`, `elements` более абстрактными формулами без необходимости.
- Для human-readable sections предметных карточек используй русский как основной язык изложения; английские domain terms сохраняй только там, где они реально являются частью продукта или source basis.
- Предпочитай живой, читаемый, domain-first аналитический стиль; не подменяй предмет карточки формулировками про wave, formalization, completeness и traceability, если эти аспекты можно вынести в `TRACE-*`, `CHANGE-*` или `MAP-*`.
- Wave-specific justification, formalization scope и cross-layer completeness должны в первую очередь жить в `CHANGE-*`, `TRACE-*` и при необходимости в `MAP-*`, а не становиться смысловым центром предметных карточек.
- Для слоя `01` фиксируй именно value movement, прикладной value outcome и anti-value для actor; не подменяй `VALUE-*` более общей product goal или process summary.

## Важные Правила По Слоям
- Для верхнеуровневого product domain layer `01` считается foundational-by-default и должен быть явно оценен до закрытия первой волны анализа.
- Молчаливый пропуск layer `01` в верхнеуровневом product domain запрещен: нужна явная причина, source basis и linked `RISK-*`.
- Child domain может не materialize локальный layer `01` только при явной фиксации inheritance или отсутствия independent value stream.
- `08-layer-requirements/` обязателен всегда: baseline `REQ-*` может жить без `HYP-*`, но инициативные `REQ-*` должны ссылаться на `HYP-*`.
- Слои `07` и `20` образуют обязательную pair-связку для scenario verification: новый `SCN-*` не остается без validating `TEST-*`, а scenario-oriented `TEST-*` не остается без ссылки на `SCN-*`.
- `24-layer-knowledge-sources/` хранит карточки источников и артефактов; сами артефакты лежат в `artifacts/`.
- `25-layer-traceability/` хранит cross-layer chains и connectivity rules, а не дублирует semantics других слоев.
- Слои `27-33` не считаются пройденными по умолчанию; для них используй связку `record_mode` / `hard_constraints_text` / `context_text`.
- Для critical path сохраняй цепочку `CRIT -> PROC/SCN -> REQ -> TEST/METRIC/PERF -> RISK/CHANGE`.

## Артефакты
- Для diagram/source artifacts заполняй `artifact_notations` и `artifact_style_reference`.
- Канонический артефакт — редактируемый source-файл в `artifacts/`; raster допустим только как preview.
- Нотации регулируются `00-meta/governance/ARTIFACT-NOTATION-GOVERNANCE-001.adoc`.

## Git И Workflow
- Здесь действует change-wave workflow: `00-meta/governance/GIT-RELEASE-WORKFLOW-001.adoc`.
- Не работай напрямую в `main`.
- До явного approval допустим только formalize-коммит `Add <scope> requirements`.
- После approval ожидаемая последовательность: `Implement <scope>` -> `Add <scope> test evidence` -> `Sync <scope> traceability`, либо `Verify and sync <scope>`.
- Не смешивай approval, implementation и verification в одном коммите.
- Не переписывай опубликованную историю; `push --force` допустим только по явному запросу пользователя.

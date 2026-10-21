# Code navigation

Paths are repository-relative. All instances are created explicitly by composition.

| Read next | Responsibility / actual target |
| --- | --- |
| `services/b-side-api/src/a2flow_bside/app.py` | Typed `create_app`, security middleware, exception mapping, owned-task lifespan and router registration |
| `services/b-side-api/src/a2flow_bside/conversation_routes.py` | Conversation/message/card HTTP handlers and owner checks |
| `services/b-side-api/src/a2flow_bside/chat_application.py` | `ChatApplicationService`: message admission, result references, processing context, saved card continuation |
| `services/b-side-api/src/a2flow_bside/processing_tasks.py` | Concrete `ProcessingTasksRepository.context_for_card`, begin_turn and processing business receipt facts |
| `services/b-side-api/src/a2flow_bside/chat_runner.py` | Genuine stream/inspection contracts; actual implementation is `deploy/attended/chat_runner.py:ChatLoopRunner` |
| `services/b-side-api/src/a2flow_bside/chat_delivery.py` | `ChatDelivery`: saved display projection and subscriber-independent production; direct/fenced `MessageProjection` |
| `services/b-side-api/src/a2flow_bside/durable_chat.py` | Concrete inbox/dispatcher, generation fencing and authoritative Runtime inspection |
| `services/b-side-api/src/a2flow_bside/run_routes.py` | Workflow/run/card/internal control HTTP handlers |
| `services/b-side-api/src/a2flow_bside/workflow_application.py` | Shared ownership/control/Runtime proxy orchestration |
| `services/b-side-api/src/a2flow_bside/account_routes.py`, `activity_routes.py`, `schedule_routes.py`, `notification_routes.py` | Other domain HTTP handlers |
| `services/b-side-api/src/a2flow_bside/route_dependencies.py`, `route_models.py`, `route_identity.py` | Explicit callback signatures, unchanged request models and authenticated identity dependency |
| `deploy/attended/bside_app.py` | Actual B object/callback construction; generic alternative is `a2flow_bside/assembly.py` |
| `deploy/realchat/launcher.py` | Real deployment entry and verified Runtime identity wrapper |
| `services/agent-workflow-runtime/src/agent_workflow_runtime/service.py`, `http.py`, `progress_http.py` | Typed Runtime service/session, HTTP lane and progress lease boundaries |

`processing_tasks.context_for_card` now resolves directly to its concrete repository.
`chat_runner.iterate` resolves to the supported port; the production composition
names `ChatLoopRunner` explicitly. Callback definitions stay beside their trusted
construction rather than being hidden in a global application registry.

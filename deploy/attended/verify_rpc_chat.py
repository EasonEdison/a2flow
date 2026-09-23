"""Opt-in proof against a newly provisioned integration environment.

Input is an operator-owned JSON file created by the isolated Java integration
launcher. It is never a public API and never calls the model provider.
"""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
from uuid import uuid4

import psycopg
from a2flow_asset_store import PostgresAssetRepository
from skillweave_contracts import TrustedContext

from agent_workflow_runtime.chat.cards import ChatCardStore
from agent_workflow_runtime.chat.rpc_actions import RpcChatActionService
from agent_workflow_runtime.chat.rpc_assets import RpcChatAssets
from agent_workflow_runtime.models import ActionRejected
from agent_workflow_runtime.rpc_assets import RpcAssetReader
from agent_workflow_runtime.rpc_client import RpcClient
from deploy.assets import bundle_validator


def assert_surface_data(card: dict, surface_id: str, expected: dict) -> None:
    updates = [message["updateDataModel"]
               for message in card["display"]["snapshotMessages"]
               if "updateDataModel" in message
               and message["updateDataModel"]["surfaceId"] == surface_id]
    assert len(updates) == 1 and updates[0]["path"] == "/", updates
    for key, value in expected.items():
        assert updates[0]["value"][key] == value, (key, updates[0]["value"])


def verify(path: Path) -> None:
    config = json.loads(path.read_text())
    dsn = config["prtDsn"]
    database = psycopg.conninfo.conninfo_to_dict(dsn)["dbname"]
    owner = TrustedContext(9223372036854775807, "PRT")
    conversation = "rpc-integration-" + uuid4().hex
    rpc = RpcClient(config["rpcTarget"], loopback_plaintext=True, timeout=20)
    repository = PostgresAssetRepository(dsn, environment="PRT", database=database,
                                         validator=bundle_validator())
    reader = RpcAssetReader(repository, config["namespace"], rpc)
    cards = ChatCardStore(dsn, environment="PRT")
    cards.setup()

    def factory(current_owner, conversation_id, control_request_id="integration-turn"):
        return RpcChatAssets(rpc=rpc, reader=reader, owner=current_owner,
                             conversation_id=conversation_id, control_request_id=control_request_id,
                             card_sink=lambda prepared, metadata: cards.save(
                                 current_owner, conversation_id, prepared, metadata))

    try:
        assets = factory(owner, conversation)
        skill = assets.admit_skill(config["skillKey"])
        assert skill["content"]["instructions"]
        assert skill["content"]["dependencies"]["applications"]
        result = assets.execute_ability(config["abilityKey"], config.get("abilityArguments", {}))
        assert result["abilityKey"] == config["abilityKey"]
        expected = config["expectedBusinessData"]
        assert config["loadBindingId"], "a real published LoadBinding is required"
        for key, value in expected.items():
            assert result["output"][key] == value, result["output"]
        card = assets.render_application(config["applicationKey"], config["params"], "render-1")
        assert card["status"] == "WAITING_ACTION", card["status"]
        assert card["display"]["snapshotMessages"]
        assert_surface_data(card, config["surfaceId"], expected)
        assert cards.read(owner, conversation, card["cardId"]) == card
        assert cards.list(TrustedContext(-9223372036854775808, "PRT"), conversation) == []
        private = cards.get_binding(owner, conversation, card["cardId"])["metadata"]
        assert private["rpc"]["session"]["token"] not in json.dumps(card)
        action = RpcChatActionService(cards, factory)
        payload = {"surfaceId": config["surfaceId"], "sourceComponentId": config["componentId"],
                   "context": config["actionContext"]}
        arguments = dict(request_id="action-1", action_name=config["actionName"],
                         inputs=payload, expected_revision=card["revision"])
        final = action.execute(owner, conversation, card["cardId"], **arguments)
        assert final["status"] == "COMPLETED", final
        assert final["result"]["businessSuccess"] is True, final["result"]
        assert_surface_data(final, config["surfaceId"], expected)
        assert action.execute(owner, conversation, card["cardId"], **arguments) == final
        reopened = ChatCardStore(dsn, environment="PRT")
        assert reopened.read(owner, conversation, card["cardId"]) == final
        try:
            action.execute(owner, conversation, card["cardId"], **{**arguments, "request_id": "second"})
            raise AssertionError("completed card accepted a second action")
        except ActionRejected:
            pass
        public_cards = path.parent / (conversation + "-public-cards.json")
        with os.fdopen(os.open(public_cards, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600), "w") as output:
            json.dump({"loadCard": card, "completedCard": final}, output, ensure_ascii=False)
        print("PUBLIC_CARDS=" + str(public_cards))
        print("RPC_CHAT_INTEGRATION_PASS: DB Skill, contracts, Ability, Load, Action, persisted refresh, exact userId, isolation, replay")
    finally:
        rpc.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--isolated-environment", type=Path, required=True)
    verify(parser.parse_args().isolated_environment)

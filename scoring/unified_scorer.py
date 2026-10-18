from __future__ import annotations

import argparse
import copy
import hashlib
import importlib.util
import json
import sys
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any, Iterable

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from common.eia_environment import EIAEnvironment as ReleasedEnvironment
from common.task_families import (
    TASK_FAMILIES,
    interface_slug,
    normalize_task_family,
    task_family_index,
)


PROFILE_REPAIR_LIMITS = {
    "P0_prompt_only": 0,
    "P2_prompt_schema_repair1": 1,
}

PROFILE_SCHEMA_TRANSPORTS = {
    "P0_prompt_only": "none",
    "P2_prompt_schema_repair1": "prompt",
}


def compact_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def object_sha256(value: Any) -> str:
    return hashlib.sha256(compact_json(value).encode("utf-8")).hexdigest()


def value_digest(value: Any) -> str:
    return object_sha256(value)


def read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    with path.open(encoding="utf-8") as handle:
        for line_number, line in enumerate(handle, 1):
            if not line.strip():
                continue
            value = json.loads(line)
            if not isinstance(value, dict):
                raise ValueError(f"{path}:{line_number} is not a JSON object")
            rows.append(value)
    return rows


def source_protocol_diagnostics(row: dict[str, Any], interface: str) -> dict[str, Any]:
    protocol = row.get("protocol") if isinstance(row.get("protocol"), dict) else {}
    profile = protocol.get("profile") if isinstance(protocol.get("profile"), str) else None
    if interface == "State-Seeking":
        format_rows = [
            turn.get("format_diagnostics")
            for turn in row.get("turns", [])
            if isinstance(turn, dict) and isinstance(turn.get("format_diagnostics"), dict)
        ]
    else:
        format_rows = [row["format_diagnostics"]] if isinstance(row.get("format_diagnostics"), dict) else []

    def all_known(key: str) -> bool | None:
        values = [item.get(key) for item in format_rows if isinstance(item.get(key), bool)]
        return None if not values else len(values) == len(format_rows) and all(values)

    repair_attempts = sum(int(item.get("repair_attempts", 0) or 0) for item in format_rows)
    declared_violations = sorted(
        {
            str(value)
            for item in format_rows
            for value in item.get("profile_violations", [])
        }
    )
    inferred_violations = list(declared_violations)
    if profile in PROFILE_REPAIR_LIMITS and repair_attempts > PROFILE_REPAIR_LIMITS[profile]:
        inferred_violations.append("repair_limit_exceeded")
    schema_enforced = protocol.get("schema_enforced")
    schema_transport = protocol.get("schema_transport")
    if profile == "P0_prompt_only" and schema_enforced is True:
        inferred_violations.append("unexpected_schema_enforcement")
    if profile in {
        "P2_prompt_schema_repair1",
    } and schema_enforced is False:
        inferred_violations.append("missing_schema_enforcement")
    expected_transport = PROFILE_SCHEMA_TRANSPORTS.get(profile)
    if (
        expected_transport is not None
        and isinstance(schema_transport, str)
        and schema_transport != expected_transport
    ):
        inferred_violations.append("schema_transport_mismatch")
    profile_compliant = None if profile is None else not inferred_violations
    telemetry = row.get("telemetry") if isinstance(row.get("telemetry"), dict) else {}
    trace = row.get("tool_trace") if isinstance(row.get("tool_trace"), list) else []
    model_turns = int(telemetry.get("model_turns", 0) or 0)
    if not model_turns:
        model_turns = sum(
            len(turn.get("attempts", []))
            for turn in row.get("turns", [])
            if isinstance(turn, dict)
        ) or (1 if interface == "State-Given" and row.get("raw_output") is not None else 0)
    return {
        "protocol_profile": profile,
        "schema_enforced": schema_enforced,
        "schema_transport": schema_transport,
        "strict_format_success": all_known("first_strict_json_valid"),
        "first_pass_schema_success": all_known("first_schema_valid"),
        "accepted_schema_success": all_known("accepted_schema_valid"),
        "repair_used": repair_attempts > 0,
        "repair_attempts": repair_attempts,
        "profile_compliant": profile_compliant,
        "profile_violations": sorted(set(inferred_violations)),
        "model_turns": model_turns,
        "decision_turns": int(telemetry.get("decision_turns", 0) or 0),
        "tool_calls": len(trace),
        "failed_tool_calls": sum(
            isinstance(item, dict) and not bool((item.get("result") or {}).get("ok"))
            for item in trace
        ),
        "duplicate_tool_calls": int(telemetry.get("duplicate_tool_calls", 0) or 0),
        "provider_usage": copy.deepcopy(telemetry.get("provider_usage")),
    }


def write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def write_jsonl(path: Path, rows: Iterable[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "".join(compact_json(row) + "\n" for row in rows), encoding="utf-8"
    )


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def load_module(path: Path, module_name: str):
    code_dir = str(path.parent.resolve())
    if code_dir not in sys.path:
        sys.path.insert(0, code_dir)
    spec = importlib.util.spec_from_file_location(module_name, path)
    if spec is None or spec.loader is None:
        raise ImportError(path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    spec.loader.exec_module(module)
    return module


def nested_delta(before: Any, after: Any, prefix: str = "") -> list[dict[str, Any]]:
    changes: list[dict[str, Any]] = []
    if isinstance(before, dict) and isinstance(after, dict):
        for key in sorted(set(before) | set(after)):
            path = f"{prefix}.{key}" if prefix else key
            if key not in before:
                changes.append({"path": path, "before": None, "after": copy.deepcopy(after[key])})
            elif key not in after:
                changes.append({"path": path, "before": copy.deepcopy(before[key]), "after": None})
            else:
                changes.extend(nested_delta(before[key], after[key], path))
    elif isinstance(before, list) and isinstance(after, list):
        if before != after:
            changes.append({"path": prefix, "before": copy.deepcopy(before), "after": copy.deepcopy(after)})
    elif before != after:
        changes.append({"path": prefix, "before": copy.deepcopy(before), "after": copy.deepcopy(after)})
    return changes


def device_state_delta(before_home: dict[str, Any], after_home: dict[str, Any]) -> list[dict[str, Any]]:
    before_devices = {d["device_id"]: d for d in before_home.get("devices", [])}
    after_devices = {d["device_id"]: d for d in after_home.get("devices", [])}
    changes: list[dict[str, Any]] = []
    for device_id in sorted(set(before_devices) | set(after_devices)):
        if device_id not in before_devices or device_id not in after_devices:
            changes.append(
                {
                    "device_id": device_id,
                    "path": "",
                    "before": copy.deepcopy(before_devices.get(device_id)),
                    "after": copy.deepcopy(after_devices.get(device_id)),
                }
            )
            continue
        for change in nested_delta(before_devices[device_id], after_devices[device_id]):
            if change["path"] == "device_id":
                continue
            changes.append({"device_id": device_id, **change})
    return sorted(changes, key=lambda row: (row["device_id"], row["path"], compact_json(row)))


def canonical_changes(changes: Any) -> list[dict[str, Any]] | None:
    if not isinstance(changes, list) or not all(isinstance(row, dict) for row in changes):
        return None
    return sorted(copy.deepcopy(changes), key=lambda row: (row.get("device_id", ""), row.get("path", ""), compact_json(row)))


class _ReleasedResultContract:
    @staticmethod
    def canonical_result(value: Any) -> Any:
        return copy.deepcopy(value)

    @staticmethod
    def strict_equal(left: Any, right: Any) -> bool:
        return left == right


def canonical_action(value: Any) -> tuple[dict[str, Any] | None, bool]:
    if not isinstance(value, dict):
        return None, False
    device_id = value.get("device_id", value.get("did"))
    service = value.get("service", value.get("locator"))
    arguments = value.get("arguments")
    normalized = set(value) != {"device_id", "service", "arguments"}
    if not isinstance(device_id, str) or not isinstance(service, str) or not isinstance(arguments, dict):
        return None, normalized
    return {"device_id": device_id, "service": service, "arguments": copy.deepcopy(arguments)}, normalized


def rule_signature(rule: Any) -> Any:
    if not isinstance(rule, dict):
        return None
    conditions = rule.get("conditions")
    actions = rule.get("actions")
    if not isinstance(conditions, dict) or not isinstance(actions, list):
        return None
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for raw_action in actions:
        action, _ = canonical_action(raw_action)
        if action is None:
            return None
        grouped[action["device_id"]].append(
            {"service": action["service"], "arguments": action["arguments"]}
        )
    return {
        "conditions": copy.deepcopy(conditions),
        "actions_by_device": {key: grouped[key] for key in sorted(grouped)},
    }


def rules_equal(actual: list[Any], expected: list[Any]) -> bool:
    actual_signatures = [rule_signature(rule) for rule in actual]
    expected_signatures = [rule_signature(rule) for rule in expected]
    if any(item is None for item in actual_signatures + expected_signatures):
        return False
    return sorted(compact_json(item) for item in actual_signatures) == sorted(
        compact_json(item) for item in expected_signatures
    )


class UnifiedScorer:
    def __init__(self, suite_root: Path, air_reviews: Path | None = None):
        self.suite_root = suite_root.resolve()
        self.released_layout = True
        self._init_released_layout(air_reviews)
    def _released_language_roots(self) -> list[Path]:
        if any((self.suite_root / family).is_dir() for family in TASK_FAMILIES):
            return [self.suite_root]
        roots = [self.suite_root / language for language in ("en", "zh") if (self.suite_root / language).is_dir()]
        if roots:
            return roots
        return [self.suite_root]

    def _init_released_layout(self, air_reviews: Path | None) -> None:
        self.environment_class = ReleasedEnvironment
        self.result_contract = _ReleasedResultContract
        self.cases = {}
        self.evaluations = {}
        self.interface_input_hashes = {"State-Given": {}, "State-Seeking": {}}
        self.id_to_tc = {}
        for root in self._released_language_roots():
            for index, family in enumerate(TASK_FAMILIES, 1):
                data_root = root / family / "data"
                cases = {row["id"]: row for row in read_jsonl(data_root / "cases.jsonl")}
                evaluations = {row["id"]: row for row in read_jsonl(data_root / "evaluation.jsonl")}
                if set(cases) != set(evaluations):
                    raise ValueError(f"{family} case/evaluation ID mismatch")
                self.cases.setdefault(index, {}).update(cases)
                self.evaluations.setdefault(index, {}).update(evaluations)
                for case_id in cases:
                    if case_id in self.id_to_tc and self.id_to_tc[case_id] != index:
                        raise ValueError(f"duplicate case ID across task families: {case_id}")
                    self.id_to_tc[case_id] = index
                for interface, directory in (("State-Given", "State-Given"), ("State-Seeking", "State-Seeking")):
                    interface_path = root / directory / "data" / f"{family}.jsonl"
                    for row in read_jsonl(interface_path):
                        self.interface_input_hashes[interface][row["id"]] = object_sha256(row)
        self.air_reviews = self._load_air_reviews(air_reviews)

    @staticmethod
    def _load_air_reviews(path: Path | None) -> dict[str, dict[str, Any]]:
        if path is None:
            return {}
        result: dict[str, dict[str, Any]] = {}
        for row in read_jsonl(path):
            required = {"id", "response_sha256", "quality", "rationale"}
            if set(row) != required or row["quality"] not in {"full", "partial", "fail"}:
                raise ValueError("invalid AIR review record")
            if row["id"] in result:
                raise ValueError(f"duplicate AIR review: {row['id']}")
            result[row["id"]] = row
        return result

    def resolve_tc(self, row: dict[str, Any]) -> int:
        tc = task_family_index(row.get("task_family"))
        case_id = row.get("id")
        inferred = self.id_to_tc.get(case_id)
        if inferred is None:
            raise KeyError(f"unknown case ID: {case_id}")
        if tc != inferred:
            raise ValueError(f"task_family mismatch for {case_id}: {tc} != {inferred}")
        return inferred

    def _new_environment(self, tc: int, case_id: str):
        return self.environment_class(self.suite_root, TASK_FAMILIES[tc - 1], case_id)

    def _normalize_state_given(
        self, row: dict[str, Any], tc: int, env
    ) -> tuple[dict[str, Any], list[dict[str, Any]], list[str], dict[str, Any]]:
        prediction = row.get("prediction")
        replay_events: list[dict[str, Any]] = []
        errors: list[str] = []
        diagnostics = {"format_normalized": False, "replay_result_count": 0}
        if not isinstance(prediction, dict):
            return {}, replay_events, ["prediction_not_object"], diagnostics

        normalized = copy.deepcopy(prediction)
        if tc in {1, 2, 3, 5, 6} and normalized.get("mode") == "execution":
            actions = normalized.get("actions")
            if not isinstance(actions, list):
                errors.append("actions_not_array")
                actions = []
            env.queried_specs.update(
                device["device_id"] for device in env.home.get("devices", [])
            )
            canonical_actions: list[dict[str, Any]] = []
            for raw_action in actions:
                action, changed = canonical_action(raw_action)
                diagnostics["format_normalized"] |= changed
                if action is None:
                    errors.append("invalid_action_shape")
                    continue
                canonical_actions.append(action)
                result = env.call("control_device", action)
                replay_events.append(
                    {"tool_name": "control_device", "arguments": action, "result": result}
                )
                if not result.get("ok"):
                    errors.append("action_execution_error")
            normalized["actions"] = canonical_actions
        elif tc == 4 and normalized.get("mode") == "automation":
            automations = normalized.get("automations")
            if not isinstance(automations, list):
                errors.append("automations_not_array")
                automations = []
            accepted: list[dict[str, Any]] = []
            for rule in automations:
                if not isinstance(rule, dict):
                    errors.append("invalid_automation_shape")
                    continue
                result = env.call("create_automation", rule)
                replay_events.append(
                    {"tool_name": "create_automation", "arguments": rule, "result": result}
                )
                if result.get("ok"):
                    accepted.append(copy.deepcopy(env.automations[-1]))
                else:
                    errors.append("automation_registration_error")
            normalized["automations"] = accepted
        diagnostics["replay_result_count"] = len(replay_events)
        return normalized, replay_events, errors, diagnostics

    def _normalize_state_seeking(
        self, row: dict[str, Any], env
    ) -> tuple[dict[str, Any], list[dict[str, Any]], list[str], dict[str, Any]]:
        final_output = row.get("final_output")
        normalized = copy.deepcopy(final_output) if isinstance(final_output, dict) else {}
        trace = row.get("tool_trace")
        errors: list[str] = []
        replay_events: list[dict[str, Any]] = []
        result_mismatches = 0
        if not isinstance(trace, list):
            trace = []
            errors.append("tool_trace_not_array")
        for item in trace:
            if not isinstance(item, dict):
                errors.append("invalid_tool_trace_item")
                continue
            name, arguments = item.get("tool_name"), item.get("arguments")
            if not isinstance(name, str) or not isinstance(arguments, dict):
                errors.append("invalid_tool_trace_item")
                continue
            actual_result = env.call(name, arguments)
            replay_events.append(
                {"tool_name": name, "arguments": copy.deepcopy(arguments), "result": actual_result}
            )
            if "result" not in item or item["result"] != actual_result:
                result_mismatches += 1
        if result_mismatches:
            errors.append("tool_result_replay_mismatch")
        recorded_initial_hash = row.get("initial_home_sha256")
        recorded_final_hash = row.get("final_home_sha256")
        initial_hash_match = (
            None if recorded_initial_hash is None else recorded_initial_hash == object_sha256(env.initial_home)
        )
        final_hash_match = (
            None if recorded_final_hash is None else recorded_final_hash == object_sha256(env.home)
        )
        if initial_hash_match is False or final_hash_match is False:
            errors.append("environment_hash_mismatch")
        diagnostics = {
            "result_replay_mismatch_count": result_mismatches,
            "initial_home_hash_present": recorded_initial_hash is not None,
            "final_home_hash_present": recorded_final_hash is not None,
            "initial_home_hash_match": initial_hash_match,
            "final_home_hash_match": final_hash_match,
        }
        return normalized, replay_events, errors, diagnostics

    def _verify(
        self,
        tc: int,
        interface: str,
        case: dict[str, Any],
        evaluation: dict[str, Any],
        prediction: dict[str, Any],
        env,
        replay_events: list[dict[str, Any]],
    ) -> dict[str, Any]:
        actual_changes = device_state_delta(env.initial_home, env.home)
        home_unchanged = env.initial_home == env.home
        control_attempts = sum(event["tool_name"] == "control_device" for event in replay_events)
        successful_controls = sum(
            event["tool_name"] == "control_device" and bool(event["result"].get("ok"))
            for event in replay_events
        )
        mode = prediction.get("mode")
        common = {
            "submitted_mode": mode,
            "actual_state_delta": actual_changes,
            "home_state_unchanged": home_unchanged,
            "control_attempt_count": control_attempts,
            "successful_control_count": successful_controls,
        }

        if tc in {1, 2, 5, 6} or (tc == 3 and evaluation["expected_mode"] == "execution"):
            expected = (
                evaluation.get("ground_truth", {}).get("expected_changes")
                if tc in {1, 2, 3}
                else evaluation.get("expected_state_delta")
            )
            expected_changes = canonical_changes(expected) or []
            comparable_actual_changes = copy.deepcopy(actual_changes)
            # TC6 Gold paths are relative to the device's state object, while
            # TC1/2/3/5 Gold paths include the leading ``state.`` segment.
            if tc == 6:
                for change in comparable_actual_changes:
                    if change["path"].startswith("state."):
                        change["path"] = change["path"][len("state.") :]
                comparable_actual_changes = canonical_changes(comparable_actual_changes) or []
            state_correct = comparable_actual_changes == expected_changes
            expected_mode = "execution"
            mode_correct = mode == expected_mode if interface == "State-Given" else mode == "completed"
            task_pass = bool(state_correct)
            return {
                **common,
                "expected_mode": expected_mode,
                "mode_correct": mode_correct,
                "state_correct": state_correct,
                "comparable_state_delta": comparable_actual_changes,
                "expected_state_delta": expected_changes,
                "task_pass": task_pass,
                "semantic_review_pending": False,
                "task_error": None if task_pass else "wrong_final_state",
            }

        if tc == 3:
            response = prediction.get("response")
            mode_correct = mode == "clarification"
            response_nonempty = isinstance(response, str) and bool(response.strip())
            structural_pass = mode_correct and response_nonempty and home_unchanged and control_attempts == 0
            review = self.air_reviews.get(case["id"])
            review_match = bool(
                review
                and isinstance(response, str)
                and review["response_sha256"] == value_digest(response)
            )
            quality = review["quality"] if review_match else None
            # Invalid protocol/state behavior is already a deterministic failure and
            # must not be held open merely because no semantic review was requested.
            semantic_pending = structural_pass and not review_match
            strict_semantic_pass = quality == "full" if quality is not None else None
            lenient_semantic_pass = (
                quality in {"full", "partial"} if quality is not None else None
            )
            if not structural_pass:
                strict_task_pass: bool | None = False
                lenient_task_pass: bool | None = False
            elif semantic_pending:
                strict_task_pass = None
                lenient_task_pass = None
            else:
                strict_task_pass = bool(strict_semantic_pass)
                lenient_task_pass = bool(lenient_semantic_pass)
            return {
                **common,
                "expected_mode": "clarification",
                "mode_correct": mode_correct,
                "clarification_response": response,
                "clarification_structural_pass": structural_pass,
                "clarification_quality": quality,
                "clarification_review_hash_match": review_match,
                "clarification_strict_semantic_pass": strict_semantic_pass,
                "clarification_lenient_semantic_pass": lenient_semantic_pass,
                "semantic_review_pending": semantic_pending,
                # The primary result follows the AIR dataset contract:
                # only a ``full`` clarification is a strict pass. ``partial`` is
                # retained as a separately reported lenient diagnostic.
                "task_pass": strict_task_pass,
                "strict_task_pass": strict_task_pass,
                "lenient_task_pass": lenient_task_pass,
                "task_error": "semantic_review_pending" if semantic_pending else (
                    None if strict_task_pass else "clarification_failed"
                ),
            }

        if tc == 4:
            expected_rules = evaluation["canonical_rules"]
            automation_correct = rules_equal(env.automations, expected_rules)
            mode_correct = mode == "automation" if interface == "State-Given" else mode == "completed"
            no_immediate_control = control_attempts == 0
            task_pass = automation_correct and home_unchanged and no_immediate_control
            return {
                **common,
                "expected_mode": "automation",
                "mode_correct": mode_correct,
                "automation_correct": automation_correct,
                "registration_state_unchanged": home_unchanged,
                "no_immediate_control": no_immediate_control,
                "actual_automations": copy.deepcopy(env.automations),
                "expected_automations": copy.deepcopy(expected_rules),
                "task_pass": task_pass,
                "semantic_review_pending": False,
                "task_error": None if task_pass else "wrong_automation",
            }

        expected_result = evaluation["expected_result"]
        result = prediction.get("result")
        try:
            answer_correct = isinstance(result, dict) and self.result_contract.strict_equal(
                self.result_contract.canonical_result(result),
                self.result_contract.canonical_result(expected_result),
            )
        except Exception:
            answer_correct = False
        mode_correct = mode == "answer"
        output_schema_compliant = "response" not in prediction
        no_mutation_attempt = control_attempts == 0
        non_mutating_compliant = home_unchanged and no_mutation_attempt
        task_pass = bool(
            mode_correct
            and answer_correct
            and output_schema_compliant
            and non_mutating_compliant
        )
        return {
            **common,
            "expected_mode": "answer",
            "mode_correct": mode_correct,
            "answer_correct": bool(answer_correct),
            "output_schema_compliant": output_schema_compliant,
            "unexpected_response_present": "response" in prediction,
            "non_mutating_compliant": non_mutating_compliant,
            "expected_result": copy.deepcopy(expected_result),
            "actual_result": copy.deepcopy(result),
            "task_pass": task_pass,
            "semantic_review_pending": False,
            "task_error": None if task_pass else "wrong_answer_schema_or_mutation",
        }

    def score_row(self, row: dict[str, Any], interface: str) -> dict[str, Any]:
        interface_key = interface_slug(interface)
        reported_interface = interface_slug(interface)
        case_id = row.get("id")
        tc = self.resolve_tc(row)
        case = self.cases[tc][case_id]
        evaluation = self.evaluations[tc][case_id]
        env = self._new_environment(tc, case_id)
        runner_error = row.get("error")
        expected_input_hash = self.interface_input_hashes[interface_key].get(case_id)
        recorded_input_hash = row.get("input_record_sha256")
        source_input_hash_match = (
            None
            if recorded_input_hash is None or expected_input_hash is None
            else recorded_input_hash == expected_input_hash
        )
        source_diagnostics = source_protocol_diagnostics(row, interface_key)

        if interface_key == "State-Given":
            prediction, replay_events, replay_errors, replay_diagnostics = self._normalize_state_given(row, tc, env)
            runtime_success = runner_error is None
            trajectory_complete = runtime_success and isinstance(row.get("prediction"), dict)
        else:
            prediction, replay_events, replay_errors, replay_diagnostics = self._normalize_state_seeking(row, env)
            runtime_failure_tokens = ("RuntimeError", "TimeoutError", "context_limit", "process")
            runtime_success = not (
                isinstance(runner_error, str)
                and any(token in runner_error for token in runtime_failure_tokens)
            )
            trajectory_complete = runner_error is None and isinstance(row.get("final_output"), dict)

        verification = self._verify(
            tc, interface_key, case, evaluation, prediction, env, replay_events
        )
        parse_success = bool(prediction)
        replay_integrity = not any(
            error in {"tool_result_replay_mismatch", "environment_hash_mismatch"}
            for error in replay_errors
        )
        if source_input_hash_match is False:
            replay_integrity = False
            replay_errors.append("input_record_hash_mismatch")
        environment_hashes_verified = True
        if interface_key == "State-Seeking":
            environment_hashes_verified = bool(
                replay_diagnostics.get("initial_home_hash_match") is True
                and replay_diagnostics.get("final_home_hash_match") is True
            )
        artifact_integrity = bool(
            source_input_hash_match is True and environment_hashes_verified
        )
        protocol_pass = bool(
            runtime_success
            and trajectory_complete
            and parse_success
            and verification.get("mode_correct")
            and replay_integrity
            and source_diagnostics["profile_compliant"] is not False
        )
        task_pass = verification["task_pass"]
        lenient_task_pass = verification.get("lenient_task_pass", task_pass)
        overall_pass = None if task_pass is None else bool(protocol_pass and task_pass)
        lenient_overall_pass = (
            None
            if lenient_task_pass is None
            else bool(protocol_pass and lenient_task_pass)
        )
        errors = list(replay_errors)
        if runner_error is not None:
            errors.append(str(runner_error))
        if not parse_success:
            errors.append("parse_failed")
        if not trajectory_complete:
            errors.append("trajectory_incomplete")
        if not verification.get("mode_correct"):
            errors.append("wrong_mode")
        if verification.get("task_error"):
            errors.append(verification["task_error"])
        if source_diagnostics["profile_compliant"] is False:
            errors.extend(source_diagnostics["profile_violations"])

        result = {
            "id": case_id,
            "subcategory": case.get("subcategory"),
            "home_type": case.get("home_type"),
            "interface": reported_interface,
            "runtime_success": runtime_success,
            "trajectory_complete": trajectory_complete,
            "parse_success": parse_success,
            "replay_integrity": replay_integrity,
            "artifact_integrity": artifact_integrity,
            "protocol_pass": protocol_pass,
            "task_pass": task_pass,
            "lenient_task_pass": lenient_task_pass,
            "overall_pass": overall_pass,
            "lenient_overall_pass": lenient_overall_pass,
            "runner_error": runner_error,
            "errors": sorted(set(errors)),
            "initial_home_sha256": object_sha256(env.initial_home),
            "final_home_sha256": object_sha256(env.home),
            "normalized_prediction": prediction,
            "replay_events": replay_events,
            "replay_diagnostics": replay_diagnostics,
            "verification": verification,
            "source_telemetry": copy.deepcopy(row.get("telemetry")),
            "source_context_budget": copy.deepcopy(row.get("context_budget")),
            "source_protocol": copy.deepcopy(row.get("protocol")),
            "source_diagnostics": source_diagnostics,
            "source_input_sha256": recorded_input_hash,
            "expected_input_sha256": expected_input_hash,
            "source_input_hash_match": source_input_hash_match,
        }
        result["task_family"] = TASK_FAMILIES[tc - 1]
        return result


def ratio(numerator: int, denominator: int) -> float | None:
    return numerator / denominator if denominator else None


def aggregate(rows: list[dict[str, Any]], interface: str) -> dict[str, Any]:
    by_group: dict[str, Any] = {}
    for tc, family in enumerate(TASK_FAMILIES, 1):
        selected = [
            row
            for row in rows
            if (
                normalize_task_family(row.get("task_family")) == family
            )
        ]
        scored = [row for row in selected if row["overall_pass"] is not None]
        pending = [row for row in selected if row["overall_pass"] is None]
        passed = sum(row["overall_pass"] is True for row in scored)
        lenient_scored = [row for row in selected if row["lenient_overall_pass"] is not None]
        lenient_passed = sum(row["lenient_overall_pass"] is True for row in lenient_scored)
        by_group[family] = {
            "count": len(selected),
            "scored_count": len(scored),
            "pending_count": len(pending),
            "passed_count": passed,
            "success_rate": ratio(passed, len(scored)),
            "lenient_scored_count": len(lenient_scored),
            "lenient_passed_count": lenient_passed,
            "lenient_success_rate": ratio(lenient_passed, len(lenient_scored)),
            "runtime_success_rate": ratio(sum(row["runtime_success"] for row in selected), len(selected)),
            "protocol_pass_rate": ratio(sum(row["protocol_pass"] for row in selected), len(selected)),
        }
    scored_all = [row for row in rows if row["overall_pass"] is not None]
    passed_all = sum(row["overall_pass"] is True for row in scored_all)
    lenient_scored_all = [row for row in rows if row["lenient_overall_pass"] is not None]
    lenient_passed_all = sum(row["lenient_overall_pass"] is True for row in lenient_scored_all)
    group_rates = [item["success_rate"] for item in by_group.values() if item["success_rate"] is not None]
    lenient_tc_rates = [
        item["lenient_success_rate"]
        for item in by_group.values()
        if item["lenient_success_rate"] is not None
    ]
    diagnostics = [row["source_diagnostics"] for row in rows]
    profiles = sorted(
        {
            item["protocol_profile"]
            for item in diagnostics
            if isinstance(item.get("protocol_profile"), str)
        }
    )

    def diagnostic_rate(key: str) -> float | None:
        values = [item[key] for item in diagnostics if isinstance(item.get(key), bool)]
        return ratio(sum(value is True for value in values), len(values))

    model_turns = [item["model_turns"] for item in diagnostics if item["model_turns"] > 0]
    total_tool_calls = sum(item["tool_calls"] for item in diagnostics)
    success_at = {
        str(limit): ratio(
            sum(
                row["overall_pass"] is True
                and row["source_diagnostics"]["model_turns"] <= limit
                for row in scored_all
            ),
            len(scored_all),
        )
        for limit in (5, 10, 20)
    }
    summary = {
        "schema_version": "edgehome-unified-score-v3",
        "interface": interface,
        "record_count": len(rows),
        "scored_count": len(scored_all),
        "pending_count": len(rows) - len(scored_all),
        "passed_count": passed_all,
        "micro_success_rate": ratio(passed_all, len(scored_all)),
        "lenient_scored_count": len(lenient_scored_all),
        "lenient_passed_count": lenient_passed_all,
        "lenient_micro_success_rate": ratio(lenient_passed_all, len(lenient_scored_all)),
        "runtime_success_rate": ratio(sum(row["runtime_success"] for row in rows), len(rows)),
        "trajectory_completion_rate": ratio(sum(row["trajectory_complete"] for row in rows), len(rows)),
        "parse_success_rate": ratio(sum(row["parse_success"] for row in rows), len(rows)),
        "protocol_pass_rate": ratio(sum(row["protocol_pass"] for row in rows), len(rows)),
        "protocol_profiles": profiles,
        "mixed_protocol_profiles": len(profiles) > 1,
        "strict_format_success_rate": diagnostic_rate("strict_format_success"),
        "first_pass_schema_success_rate": diagnostic_rate("first_pass_schema_success"),
        "accepted_schema_success_rate": diagnostic_rate("accepted_schema_success"),
        "repair_usage_rate": diagnostic_rate("repair_used"),
        "repair_attempts": sum(item["repair_attempts"] for item in diagnostics),
        "model_turns_mean": sum(model_turns) / len(model_turns) if model_turns else None,
        "model_turns_max": max(model_turns) if model_turns else None,
        "success_at": success_at,
        "tool_calls": total_tool_calls,
        "failed_tool_calls": sum(item["failed_tool_calls"] for item in diagnostics),
        "duplicate_tool_calls": sum(item["duplicate_tool_calls"] for item in diagnostics),
        "failed_tool_call_rate": ratio(
            sum(item["failed_tool_calls"] for item in diagnostics), total_tool_calls
        ),
        "error_counts": dict(sorted(Counter(error for row in rows for error in row["errors"]).items())),
        "formal_report_ready": (
            len(rows) > 0
            and len(rows) == len(scored_all)
            and all(row["artifact_integrity"] for row in rows)
            and len(profiles) <= 1
        ),
    }
    macro_rate = sum(group_rates) / len(group_rates) if group_rates else None
    lenient_macro_rate = sum(lenient_tc_rates) / len(lenient_tc_rates) if lenient_tc_rates else None
    summary["task_family_macro_success_rate"] = macro_rate
    summary["lenient_task_family_macro_success_rate"] = lenient_macro_rate
    summary["by_task_family"] = by_group
    return summary


def markdown_report(summary: dict[str, Any]) -> str:
    def percent(value: float | None) -> str:
        return "pending" if value is None else f"{value * 100:.2f}%"

    macro_key = "task_family_macro_success_rate"
    lenient_macro_key = "lenient_task_family_macro_success_rate"
    lines = [
        "# EdgeBench-Home Evaluation",
        "",
        f"- Interface: `{summary['interface']}`",
        f"- Records: `{summary['record_count']}`",
        f"- Scored: `{summary['scored_count']}`",
        f"- Pending semantic review: `{summary['pending_count']}`",
        f"- Micro success: `{percent(summary['micro_success_rate'])}`",
        f"- Task-family macro success: `{percent(summary[macro_key])}`",
        f"- Lenient micro success: `{percent(summary['lenient_micro_success_rate'])}`",
        f"- Lenient task-family macro success: `{percent(summary[lenient_macro_key])}`",
        f"- Formal report ready: `{summary['formal_report_ready']}`",
        "",
        "| Task family | Count | Scored | Pending | Strict passed | Strict success | Lenient passed | Lenient success |",
        "|---|---:|---:|---:|---:|---:|---:|---:|",
    ]
    groups = summary.get("by_task_family", {})
    for task_family, item in groups.items():
        lines.append(
            f"| {task_family.upper()} | {item['count']} | {item['scored_count']} | "
            f"{item['pending_count']} | {item['passed_count']} | {percent(item['success_rate'])} | "
            f"{item['lenient_passed_count']} | {percent(item['lenient_success_rate'])} |"
        )
    lines.extend(
        [
            "",
            "## Diagnostic rates",
            "",
            f"- Runtime success: `{percent(summary['runtime_success_rate'])}`",
            f"- Trajectory completion: `{percent(summary['trajectory_completion_rate'])}`",
            f"- Parse success: `{percent(summary['parse_success_rate'])}`",
            f"- Protocol pass: `{percent(summary['protocol_pass_rate'])}`",
            f"- Protocol profiles: `{', '.join(summary['protocol_profiles']) or 'legacy/unknown'}`",
            f"- Strict raw format: `{percent(summary['strict_format_success_rate'])}`",
            f"- First-pass schema: `{percent(summary['first_pass_schema_success_rate'])}`",
            f"- Accepted schema: `{percent(summary['accepted_schema_success_rate'])}`",
            f"- Repair usage: `{percent(summary['repair_usage_rate'])}`",
            f"- Success@5: `{percent(summary['success_at']['5'])}`",
            f"- Success@10: `{percent(summary['success_at']['10'])}`",
            f"- Success@20: `{percent(summary['success_at']['20'])}`",
            f"- Mean model turns: `{summary['model_turns_mean']}`",
            f"- Tool calls / failed / duplicate: `{summary['tool_calls']} / {summary['failed_tool_calls']} / {summary['duplicate_tool_calls']}`",
            "",
            (
                "AIR clarification records remain pending until a response-hash-bound "
                "semantic review file is supplied."
                if summary["pending_count"]
                else "AIR semantic review is complete; no clarification records are pending."
            ),
            "",
        ]
    )
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Normalize, replay, and score EdgeBench-Home State-Given or State-Seeking outputs."
    )
    parser.add_argument("--suite-root", type=Path, required=True)
    parser.add_argument(
        "--interface",
        required=True,
        help="State-Given or State-Seeking.",
    )
    parser.add_argument("--predictions", type=Path, nargs="+", required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--air-reviews", type=Path)
    parser.add_argument(
        "--require-complete",
        action="store_true",
        help="Exit non-zero if AIR semantic reviews are pending.",
    )
    args = parser.parse_args()

    prediction_rows: list[dict[str, Any]] = []
    seen: set[str] = set()
    for path in args.predictions:
        for row in read_jsonl(path):
            case_id = row.get("id")
            if not isinstance(case_id, str) or case_id in seen:
                raise ValueError(f"invalid or duplicate prediction ID: {case_id}")
            seen.add(case_id)
            prediction_rows.append(row)

    scorer = UnifiedScorer(args.suite_root, args.air_reviews)
    normalized_interface = interface_slug(args.interface)
    results = [scorer.score_row(row, normalized_interface) for row in prediction_rows]
    summary = aggregate(results, normalized_interface)
    args.output_dir.mkdir(parents=True, exist_ok=True)
    write_jsonl(args.output_dir / "score_records.jsonl", results)
    write_json(args.output_dir / "summary.json", summary)
    (args.output_dir / "report.md").write_text(markdown_report(summary), encoding="utf-8")
    write_json(
        args.output_dir / "run_manifest.json",
        {
            "schema_version": "edgehome-unified-score-run-v3",
            "interface": normalized_interface,
            "protocol_profiles": summary["protocol_profiles"],
            "suite_root": str(args.suite_root.resolve()),
            "prediction_files": [
                {"path": str(path.resolve()), "sha256": file_sha256(path)}
                for path in args.predictions
            ],
            "air_reviews": (
                None
                if args.air_reviews is None
                else {
                    "path": str(args.air_reviews.resolve()),
                    "sha256": file_sha256(args.air_reviews),
                }
            ),
        },
    )
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    if args.require_complete and not summary["formal_report_ready"]:
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

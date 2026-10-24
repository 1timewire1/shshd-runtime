"""Compact transport schemas. Semantic limits are also enforced by the workspace."""
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field


class Edit(BaseModel):
    model_config = ConfigDict(extra='forbid', strict=True)
    op: Literal['project', 'node', 'character', 'connect', 'rename_node', 'image', 'audio', 'library_image', 'asset_label', 'layout']
    id: str | int | None = Field(default=None, description='Node/character ID, or integer asset ID for asset_label.')
    changes: dict[str, Any] = Field(default_factory=dict, description='Fields to patch for project/node/character. Get node fields and valid examples with schema_get.')
    remove: bool = Field(default=False, description='For node/character only. Reconnect all references in the same batch.')
    new_id: str | None = Field(default=None, description='New identity for rename_node; updates edges, start and translation keys.')
    source: str | None = Field(default=None, description='Source node for connect; workspace-relative PNG/JPEG file for image, MP3/WAV file for audio.')
    target: str | None = Field(default=None, description='Destination node for connect. May be created later in this batch.')
    field: str = Field(default='next', description='Connection field: next, otherwise or options.N.target; default next.')
    library: str | None = Field(default=None, description='Workspace-relative imported library directory for library_image.')
    resource: int | None = Field(default=None, description='Exact resource ID, integer 0–32767, for library_image.')
    episode: str | None = Field(default=None, description='Episode ID returned by asset_list_episodes; omit for a base image.')
    label: str | None = Field(default=None, description='User label for asset_label, at most 1000 characters.')


class ScenarioStep(BaseModel):
    model_config = ConfigDict(extra='forbid', strict=True)
    action: Literal['run', 'choose', 'continue', 'answer_text', 'answer', 'tick', 'step', 'grid_pointer']
    until: Literal['input', 'choice', 'end', 'node'] = 'input'
    node_id: str | None = None
    option_id: str | None = Field(default=None, description='For choose: exact enabled option ID returned by a playtest, stable within this project revision.')
    value: str | int | None = None
    milliseconds: int = Field(default=0, ge=0, le=60000, description='For tick: integer 0–60000 milliseconds; default 0.')
    phase: Literal['down', 'move', 'up', 'cancel'] | None = None
    cell: int | None = None


class Assertion(BaseModel):
    model_config = ConfigDict(extra='forbid', strict=True)
    kind: Literal['variable', 'text_variable', 'node', 'action', 'visited', 'ended']
    name: str | None = None
    equals: str | int | None = None
    node_id: str | None = None


class Scenario(BaseModel):
    model_config = ConfigDict(extra='forbid', strict=True)
    seed: int = Field(default=0, ge=0, le=4294967295, description='Reproducible unsigned 32-bit seed, 0–4294967295; default 0.')
    start: str | None = Field(default=None, description='Optional authored starting node; imported native entry points stay fixed.')
    language: Literal['en', 'fr', 'it', 'de', 'es'] | None = None
    steps: list[ScenarioStep] = Field(max_length=200, description='At most 200 real input operations. Stops on errors, unsupported calls or budgets.')
    assertions: list[Assertion] = Field(default_factory=list, max_length=200, description='At most 200 checks against the final state or visited nodes.')

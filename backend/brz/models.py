from typing import Annotated, Literal
from pydantic import AfterValidator, BaseModel, ConfigDict, Field


def validate_python_source(value: str) -> str:
    if not value.strip() or len(value.encode("utf-8")) > 64 * 1024:
        raise ValueError("Code must be nonempty and at most 64 KiB")
    return value


PythonSource = Annotated[
    str, Field(min_length=1, max_length=64 * 1024), AfterValidator(validate_python_source)
]


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)


class CodeRequest(StrictModel):
    kind: Literal["code"]
    code_payload: PythonSource
    upload_id: str | None = Field(default=None, pattern=r"^[a-f0-9]{32}$")


class TaskRequest(StrictModel):
    kind: Literal["task"]
    pattern: Literal["code", "browser"]
    prompt: str = Field(min_length=1, max_length=4000)
    upload_id: str | None = Field(default=None, pattern=r"^[a-f0-9]{32}$")


class PresetRequest(StrictModel):
    kind: Literal["preset"]
    preset_id: str = Field(min_length=1, max_length=64)
    upload_id: str | None = Field(default=None, pattern=r"^[a-f0-9]{32}$")


ExecuteRequest = Annotated[CodeRequest | TaskRequest | PresetRequest, Field(discriminator="kind")]


class CodePlan(StrictModel):
    code: PythonSource


class BrowserPlan(StrictModel):
    kind: Literal["research", "prepare_form"]
    url: str = Field(default="", max_length=2048)
    title: str = Field(default="Demo request", max_length=120)
    message: str = Field(default="", max_length=2000)


class SubmitRequest(StrictModel):
    action_id: str = Field(pattern=r"^[a-f0-9]{32}$")
    permit: str = Field(min_length=32, max_length=128)
    title: str = Field(min_length=1, max_length=120)
    message: str = Field(max_length=2000)
    revision: str = Field(min_length=1, max_length=128)

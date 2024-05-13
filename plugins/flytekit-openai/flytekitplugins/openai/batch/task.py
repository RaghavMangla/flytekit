from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Iterator, Optional

import jsonlines
from mashumaro.mixins.json import DataClassJSONMixin

import flytekit
from flytekit import Resources, kwtypes, lazy_module
from flytekit.configuration import SerializationSettings
from flytekit.configuration.default_images import DefaultImages, PythonVersion
from flytekit.core.base_task import PythonTask
from flytekit.core.interface import Interface
from flytekit.core.python_customized_container_task import PythonCustomizedContainerTask
from flytekit.core.shim_task import ShimTaskExecutor
from flytekit.extend.backend.base_agent import AsyncAgentExecutorMixin
from flytekit.models.task import TaskTemplate
from flytekit.types.file import JSONLFile
from flytekit.types.iterator import JSON

from .agent import OPENAI_API_KEY

openai = lazy_module("openai")


@dataclass
class BatchResult(DataClassJSONMixin):
    output_file: Optional[JSONLFile] = None
    error_file: Optional[JSONLFile] = None


class BatchEndpointTask(AsyncAgentExecutorMixin, PythonTask):
    _TASK_TYPE = "openai-batch"

    def __init__(
        self,
        name: str,
        openai_organization: str,
        config: Dict[str, Any] = {},
        **kwargs,
    ):
        super().__init__(
            name=name,
            task_type=self._TASK_TYPE,
            interface=Interface(
                inputs=kwtypes(input_file_id=str),
                outputs=kwtypes(result=Dict),
            ),
            **kwargs,
        )

        self._openai_organization = openai_organization
        self._config = config

    def get_custom(self, settings: SerializationSettings) -> Dict[str, Any]:
        return {
            "openai_organization": self._openai_organization,
            "config": self._config,
        }


class OpenAIFileDefaultImages(DefaultImages):
    """Default images for the openai batch plugin."""

    _DEFAULT_IMAGE_PREFIXES = {
        PythonVersion.PYTHON_3_8: "cr.flyte.org/flyteorg/flytekit:py3.8-openai-batch-",
        PythonVersion.PYTHON_3_9: "cr.flyte.org/flyteorg/flytekit:py3.9-openai-batch-",
        PythonVersion.PYTHON_3_10: "cr.flyte.org/flyteorg/flytekit:py3.10-openai-batch-",
        PythonVersion.PYTHON_3_11: "cr.flyte.org/flyteorg/flytekit:py3.11-openai-batch-",
        PythonVersion.PYTHON_3_12: "cr.flyte.org/flyteorg/flytekit:py3.12-openai-batch-",
    }


@dataclass
class OpenAIFileConfig:
    openai_organization: str


class UploadJSONLFileTask(PythonCustomizedContainerTask[OpenAIFileConfig]):
    _UPLOAD_JSONL_FILE_TASK_TYPE = "openai-batch-upload-file"

    def __init__(
        self,
        name: str,
        task_config: OpenAIFileConfig,
        # container_image: str = OpenAIFileDefaultImages.default_image(),
        container_image: str = "samhitaalla/openai-batch-file:0.0.2",
        **kwargs,
    ):
        super().__init__(
            name=name,
            task_config=task_config,
            task_type=self._UPLOAD_JSONL_FILE_TASK_TYPE,
            executor_type=UploadJSONLFileExecutor,
            container_image=container_image,
            requests=Resources(mem="700Mi"),
            interface=Interface(
                inputs=kwtypes(
                    json_iterator=Optional[Iterator[JSON]],
                    jsonl_file=Optional[JSONLFile],
                ),
                outputs=kwtypes(result=str),
            ),
            **kwargs,
        )

    def get_custom(self, settings: SerializationSettings) -> Dict[str, Any]:
        return {"openai_organization": self.task_config.openai_organization}


class UploadJSONLFileExecutor(ShimTaskExecutor[UploadJSONLFileTask]):
    def execute_from_model(self, tt: TaskTemplate, **kwargs) -> Any:
        client = openai.OpenAI(
            organization=tt.custom["openai_organization"],
            api_key=flytekit.current_context().secrets.get(group=OPENAI_API_KEY),
        )

        if kwargs.get("jsonl_file"):
            local_jsonl_file = kwargs["jsonl_file"].download()
        elif kwargs.get("json_iterator"):
            local_jsonl_file = str(Path(flytekit.current_context().working_directory, "local.jsonl"))
            with open(local_jsonl_file, "w") as w:
                with jsonlines.Writer(w) as writer:
                    for json_val in kwargs["json_iterator"]:
                        writer.write(json_val)

        # The file can be a maximum of 512 MB
        uploaded_file_obj = client.files.create(file=open(local_jsonl_file, "rb"), purpose="batch")
        return uploaded_file_obj.id


class DownloadJSONFilesTask(PythonCustomizedContainerTask[OpenAIFileConfig]):
    _DOWNLOAD_JSON_FILES_TASK_TYPE = "openai-batch-download-files"

    def __init__(
        self,
        name: str,
        task_config: OpenAIFileConfig,
        # container_image: str = OpenAIFileDefaultImages.default_image(),
        container_image: str = "samhitaalla/openai-batch-file:0.0.2",
        **kwargs,
    ):
        super().__init__(
            name=name,
            task_config=task_config,
            task_type=self._DOWNLOAD_JSON_FILES_TASK_TYPE,
            executor_type=DownloadJSONFilesExecutor,
            container_image=container_image,
            requests=Resources(mem="700Mi"),
            interface=Interface(
                inputs=kwtypes(batch_endpoint_result=Dict),
                outputs=kwtypes(result=BatchResult),
            ),
            **kwargs,
        )

    def get_custom(self, settings: SerializationSettings) -> Dict[str, Any]:
        return {"openai_organization": self.task_config.openai_organization}


class DownloadJSONFilesExecutor(ShimTaskExecutor[DownloadJSONFilesTask]):
    def execute_from_model(self, tt: TaskTemplate, **kwargs) -> Any:
        client = openai.OpenAI(
            organization=tt.custom["openai_organization"],
            api_key=flytekit.current_context().secrets.get(group=OPENAI_API_KEY),
        )

        batch_result = BatchResult()
        working_dir = flytekit.current_context().working_directory

        for file_name, file_id in zip(
            ("output_file", "error_file"),
            (
                kwargs["batch_endpoint_result"]["output_file_id"],
                kwargs["batch_endpoint_result"]["error_file_id"],
            ),
        ):
            if file_id:
                file_content = client.files.content(file_id)

                file_path = str(Path(working_dir, file_name).with_suffix(".jsonl"))
                file_content.stream_to_file(file_path)

                setattr(batch_result, file_name, JSONLFile(file_path))

        return batch_result

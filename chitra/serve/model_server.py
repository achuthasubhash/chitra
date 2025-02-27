import itertools
from functools import partial
from typing import Callable, Optional

import uvicorn
from fastapi import FastAPI, File, UploadFile

from .data_processing import DataProcessor, DefaultProcessor
from .schema import QnARequest, Query

IMAGE_CLF = "IMAGE-CLASSIFICATION"
OBJECT_DETECTION = "OBJECT-DETECTION"
TXT_CLF = "TEXT-CLASSIFICATION"
QNA = "QUESTION-ANS"

API_TYPES = {"VISION": (IMAGE_CLF, OBJECT_DETECTION), "NLP": (TXT_CLF, QNA)}


def get_available_api_types():
    return list(itertools.chain.from_iterable(API_TYPES.values()))


class ModelServer:
    def __init__(
        self,
        api_type: str,
        model: Callable,
        preprocess_fn=None,
        postprocess_fn=None,
        **kwargs,
    ):
        self.api_type = api_type.upper()
        self.model = model
        self.data_processor: Optional[DataProcessor] = self.set_data_processor(
            preprocess_fn, postprocess_fn
        )

    @staticmethod
    def set_data_processor(preprocess_fn: Callable, postprocess_fn: Callable):
        if (preprocess_fn or postprocess_fn) is None:
            return None
        data_processor = DataProcessor(preprocess_fn, postprocess_fn)
        return data_processor

    def set_default_processor(self) -> DataProcessor:
        api_type = self.api_type
        if api_type in API_TYPES.get("VISION"):
            self.data_processor = DefaultProcessor.vision
        elif api_type in API_TYPES.get("NLP"):
            self.data_processor = DefaultProcessor.nlp
        else:
            raise UserWarning(
                f"{api_type} is not implemented! Available types are - {get_available_api_types()}"
            )
        return self.data_processor


class API(ModelServer):
    def __init__(
        self,
        api_type: str,
        model: Callable,
        preprocess_fn: Callable = None,
        postprocess_fn: Callable = None,
        **kwargs,
    ):
        super(API, self).__init__(
            api_type, model, preprocess_fn, postprocess_fn, **kwargs
        )
        docs_url = kwargs.get("docs_url", "/docs")
        title = kwargs.get("title", "Chitra Model Server 🔥")
        desc = kwargs.get(
            "description",
            '<a href="https://chitra.readthedocs.io/en/latest">Goto Chitra Docs</a> 🔗',
        )
        self.app = FastAPI(title=title, description=desc, docs_url=docs_url)
        self.setup_api(**kwargs)

    async def predict_image(self, file: UploadFile = File(...)):
        preprocess_fn = self.data_processor.preprocess_fn
        postprocess_fn = self.data_processor.postprocess_fn

        x = preprocess_fn(await file.read())
        x = self.model(x)
        x = postprocess_fn(x)
        return x

    async def predict_text(self, data: Query):
        data_processor = self.data_processor
        x = data.query
        if data_processor.preprocess_fn:
            x = data_processor.preprocess(x)
        x = self.model(x)
        if data_processor.postprocess_fn:
            x = data_processor.postprocess(x)
        return x

    async def predict_question_answer(self, data: QnARequest):
        data_processor = self.data_processor
        x = data.query, data.question
        if data_processor.preprocess_fn:
            x = data_processor.preprocess(x)
        x = self.model(x)
        if data_processor.postprocess_fn:
            x = data_processor.postprocess(x)
        return x

    def setup_api(self, **kwargs):
        if self.data_processor is None:
            data_processor = self.set_default_processor()
            data_processor.preprocess_fn = partial(
                data_processor.preprocess_fn, **kwargs
            )
            data_processor.postprocess_fn = partial(
                data_processor.postprocess_fn, **kwargs
            )
            self.data_processor = data_processor

        if self.api_type == IMAGE_CLF:
            self.app.post("/api/predict-image")(self.predict_image)

        elif self.api_type == TXT_CLF:
            self.app.post("/api/predict-text")(self.predict_text)

        elif self.api_type == QNA:
            self.app.post("/api/QnA")(self.predict_question_answer)

    def run(self):
        uvicorn.run(self.app)


def create_api(
    model: Callable,
    api_type: str = "IMAGE-CLASSIFICATION",
    preprocess: Optional[Callable] = None,
    postprocess: Optional[Callable] = None,
    run: bool = False,
    **kwargs,
) -> FastAPI:
    """
    Create ASGI API with using FastAPI.
    Args:
        model[Callable]: any callable model -> pred = model(x)
        api_type[str]: Type of API to be created -> {"IMAGE-CLASSIFICATION", "TEXT-CLASSIFICATION", "QUESTION-ANS"}
        preprocess[Callable]: Preprocessing function for your data. (Default fn will be applied if None.)
        postprocess[Callable]: Postprocessing function for your data. (Default fn will be applied if None.)
        run[bool]: Whether to the the API or not.
        **kwargs:
            image_size[tuple]: if the api type is image-classification then size of target image.
    Returns:
        FastAPI app
    """
    api = API(api_type, model, preprocess, postprocess, **kwargs)

    if run:
        api.run()
    return api

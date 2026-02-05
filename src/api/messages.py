import spacy
from pydantic import StrictStr, field_validator
from pydantic.dataclasses import dataclass


# typedef for the citation field to make annotations more concise
CitationType = dict[StrictStr, float] | None

# Pydantic dataclasses for the API endpoints

@dataclass
class AssistantResponse:
    """
    This defines the format of the object that the clients should send to 
    the /continue endpoint.
    """
    run_id: StrictStr
    response: StrictStr
    # citations may or may not be provided and can have multiple formats.
    # note that this is validated using check_citations below.
    citations: CitationType = None
    # ptkb provenance listing may or may not be provided
    ptkb_provenance: list[StrictStr] | None = None

    _nlp = spacy.blank("en")

    @field_validator("response", mode="before")
    @classmethod
    def check_response(cls, value: StrictStr) -> StrictStr:
        doc = cls._nlp(value)
        if len(doc) <= 250:
            return value

        raise ValueError(
            f"Response is too long ({len(doc)} tokens). Response exceeds limit of 250 tokens."
        )


    @field_validator("citations", mode="before")
    @classmethod
    def check_citations(cls, value: CitationType) -> CitationType:
        """
        Due to some implicit type conversion that goes on before the request
        payload reaches pydantic, it seems to be possible for invalid dicts like
        {123: 456} to be accepted as valid citation values (the key is auto-cast
        to string).

        To prevent this from happening, this validator examines each key of a supplied dict and rejects
        it if it doesn't match.
        """
        if isinstance(value, dict):
            for k in value.keys():
                if not isinstance(k, str):
                    raise ValueError(
                        f"Citations key {k} is invalid (should start with 'clueweb'))"
                    )
        return value


@dataclass
class UserUtterance:
    """
    This defines the format of the object that the API sends back to the
    client system when a request arrives at the /start or /continue endpoints.
    """
    timestamp: StrictStr
    run_id: StrictStr
    topic_id: StrictStr
    user_id: StrictStr
    utterance: StrictStr
    history: list[dict[StrictStr, StrictStr]]
    last_response_of_session: bool
    last_response_of_run: bool


@dataclass
class RunMeta:
    """
    This defines the format of the object that the clients should send
    to the /start endpoint to kick off a run.
    """
    run_id: StrictStr
    description: StrictStr
    track_persona: bool = False
    team_id: StrictStr | None = None

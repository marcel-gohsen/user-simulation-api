# Sim.API

![Dynamic TOML Badge](https://img.shields.io/badge/dynamic/toml?url=https%3A%2F%2Fraw.githubusercontent.com%2Fmarcel-gohsen%2Fuser-simulation-api%2Frefs%2Fheads%2Fmain%2Fpyproject.toml&query=%24.project.version&label=version) ![Python Version from PEP 621 TOML](https://img.shields.io/python/required-version-toml?tomlFilePath=https%3A%2F%2Fraw.githubusercontent.com%2Fmarcel-gohsen%2Fuser-simulation-api%2Frefs%2Fheads%2Fmain%2Fpyproject.toml)

Sim.API is a middleware to connect participant systems and user simulators for shared tasks in conversational search. 

## Deployment

Sim.API can be installed either directly as a standalone Python application or as a Docker container.

### Option 1 (from source code)

Installing from source code requires [Poetry](https://python-poetry.org/) to be installed. 

```shell
poetry install
```

The server can be started with the following command. Provide the credentials of an admin account, which can be used to register new teams. The shared task name can be configured by the organizers.
```shell
poetry run serve --admin-name <admin_name> --admin-password <admin_password> --shared-task <shared_task>
```

### Option 2 (from Docker image)

There is a CUDA-based prebuilt Docker image available to deploy the Sim.API. To access the database from outside of the built container it makes sense to mount the database path to the host system. 

```shell
docker run [--gpus all] -p 8888:8888\
  -v <host_path>:/app/database\
  -e ADMIN_NAME=<admin_name>\
  -e ADMIN_PASSWORD=<admin_password>\
  -e SHARED_TASK=<shared_task>\ 
  registry.webis.de/code-lib/public-images/user-simulation-api:latest
```

Changes to the source code require a rebuild of the image for which there is a Makefile routine. 

```shell
make docker_build
```

## Instructions for Organizers

> Note: The following instructions assume that the API is deployed at `localhost:8888/simulation`. This is likely going to change when the API is deployed in practice and the documentation for participants has to be adjusted accordingly. 

### Configuring Topics and User Simulators

To configure a new shared task, the `shared_task.shared_task.SharedTask` class has to be implemented. The class is defined as shown below.

```python
class SharedTask(metaclass=ABCMeta):
    """Abstract class to configure shared tasks."""
    
    name: str
    topics: OrderedDict[str, Topic]
    users_per_topic: Dict[str, List[simulation.user.User]]
    debug_users_per_topic: Dict[str, List[simulation.user.User]]


    @abstractmethod
    def initialize(self):
        pass
```

A unique `name` has to be assigned, which is provided as command line parameter at the server run command to select the new shared task. The `topics` is an ordered dictionary (order is defined by order of insertion) that maps from topic id to the actual topic object. The `users_per_topic` and `debug_users_per_topic` should provide a mapping between topic ids and corresponding user simulation implementation that should be used for that given topic in the run submission or playground, respectively. If multiple implementations are specified for a given topic, a random one is assigned during runs. 

To add additional user simulators the `simulation.user.User` class has to be overridden. 

```python
class User(metaclass=abc.ABCMeta):

    @abc.abstractmethod
    def initiate(self, topic_id: str) -> str:
        pass

    @abc.abstractmethod
    def respond(self, topic_id, subtopics: List[str], messages: List[Dict[str, Any]]) -> Tuple[str, Optional[str], Optional[int]]:
        pass
```

The User class has two methods `initiate()` and `respond()`, which are responsible for producing the initial utterance based on a topic and responding to system answers, respectively.

### Configuring Budget Limits

To configure budget limits and documentation strings, the `config/api-conf.yml` file can be adjusted. 

```yaml
  debug:
    name: "debug"
    limits:
      value: 100
      unit: sessions
  ...
  run:
    name: "run"
    limits:
      value: 100
      unit: runs
```

### Registering a New Team

Administrators can register new teams by an authorized request to the `/auth/issue-token` endpoint. An example request with curl could look like the following. The `<auth_secret>` is the base64-encoded admin credentials as `<admin_name>:<admin_password>` as defined at server execution.

```shell
curl "localhost:8888/simulation/auth/issue-token?name=team-id" -H "Authorization: Basic <auth_secret>"
```

In response, a json object with a token is supplied.

```json
{"token":  "<token>"}
```

```shell
curl "localhost:8888/simulation/auth/issue-token?name=team-id" -H "Authorization: Basic <auth_secret>"
```

### Exporting Run Files

A call to the `/run/dump-all` endpoint will export all run submission of all teams in a TREC'25-compliant run file format. This action requires admin privileges. 

```shell
curl "localhost:8888/simulation/run/dump-all" -H "Authorization: Basic <auth_secret>"
```

## Instructions for Participants

This API can be used for two main purposes:
1. [Submitting runs for the shared task](#submitting-runs). 
2. [Developing, debugging and testing of systems in the playground](#debugging--testing-a-system).

### Authentication

Participants need to be registered to a shared task in order to use this API. As a result, participants will receive a base64-encoded access token from the organizers. 

All requests to this API have to be authenticated. Participants can authenticate themselves by providing their access token in the HTTP `Authorization` header. 

You can test if your access token is valid by calling the following method:
```bash
curl -H "Authorization: Bearer <token>" localhost:8888/simulation/auth/verify
```

If your token is valid, the API will respond with:
```json
{"team_id":  "<TEAM_ID>"}
```

### Submitting Runs

<span style="color: red">**Important:**</span> With the following information the final participant runs will be submitted. For debugging and developing participant systems refer to [this information below](#debugging--testing-a-system).  

Conversations are always user-initiated. In a first step, participants submit meta-information about their run and receive the first user utterance for the first topic. From there, participants and the simulated user take turns in responding to each other's utterances. Users terminate the conversations and switch topics automatically.

#### 1. Starting a Run

Participants start a run by providing the following run meta-information and in turn receive the first user utterance for the first topic. 

Please provide the following meta-information:
* `run_id`: Unique name that identifies your run. Please choose a meaningful name (e.g., `teamA-llama3-dense-retrieval`).
* `description`: Brief description of the used approach in this run. 
* `track_persona`: Indicate if your approach extracts and keeps track of persona statements of reoccurring users. 

An example request looks like this:
```bash
curl -X POST -H "Authorization: Bearer <token>" -H "Content-Type: application/json" -d \
 '{
    "run_id": "teamA-llama3-dense-retrieval",
    "description": "The approach uses a retrieval-augmented generation pipeline with llama3.3 70B as generation backbone and a dense retrieval approach for the retrieval of relevant passages.", 
     "track_persona": false
  }' localhost:8888/simulation/run/start
```

A response to a successful request looks like this:
```json
{
  "timestamp":"2025-05-06T10:58:33.400920",
  "run_id":"teamA-llama3-dense-retrieval",
  "topic_id":"1-1",
  "user_id":"f3333f5c-8313-4941-beea-f24de25a583a",
  "utterance":"Show me universities with computer science programs.",
  "history":[
    {"role":"user","content":"Show me universities with computer science programs."}
  ],
  "last_response_of_session":false,
  "last_response_of_run":false
}
```
Responses contain the following fields:
* `timestamp`: Time and date of the current response.
* `run_id`: The chosen identifier for the run.
* `topic_id`: Id of the current topic of TREC iKAT 2025 test set. 
* `user_id`: Uuid4 that identifies a (simulated) user the system talks with. This helps to identify reoccurring users. 
* `utterance`: Current utterance of the user.
* `history`: A list of the current and prior utterances in LLM-compatible format that can be used to track the current context of the conversation. 
* `last_response_of_session`: Flag that indicates that the current session (for the current topic) is terminated by the user. If true, the next response will be about a new topic. 
* `last_response_of_run`: Flag that indicates that the current session is terminated by the user and that there are no open topics left. If true, your run is completed and successfully submitted.  

#### 2. Responding to User Utterances

After a run is started like shown above, participants receive the first user utterance. From now until the run is completed, participants respond to user utterances by calling the `run/continue` endpoint. Participants should always provide the following information: 
* `run_id`: The chosen identifier for the run.
* `response`: The generated response of the system.
* `citations`: The (up to) top 1000 relevant passages given as their ids and their relevance score. 
* `ptkb_provenance`: (Optional) PTKB statements that are considered relevant for the current turn. 


An example request looks like this:
```bash
curl -X POST -H "Authorization: Bearer <token>" -H "Content-Type: application/json" -d\
 '{
   "run_id": "teamA-llama3-dense-retrieval", 
   "response": "There is University of Amsterdam.",
   "citations": {
     "clueweb22-en0032-04-00208:7": 0.8, 
     "clueweb22-en0027-84-11778:0": 0.4
   },
   "ptkb_provenance": [
     "I live in the Netherlands."
   ]
  }' localhost:8888/simulation/run/continue
```

Successful requests always result in responses formatted as mentioned above. 

```json
{
  "timestamp":"2025-05-06T11:16:53.306006","run_name":"teamA-llama3-dense-retrieval",
  "topic_id":"1-1",
  "user_id":"f3333f5c-8313-4941-beea-f24de25a583a",
  "utterance":"That’s a good start, but the initial response wasn’t helpful. Could you specifically tell me which programs at the University of Amsterdam emphasize courses similar to the ones I enjoyed during my bachelor’s degree – specifically data structures, algorithms, data mining, and artificial intelligence?",
  "history":[
    {"role":"user","content":"Show me universities with computer science programs."},
    {"role":"assistant","content":"University of Amsterdam"},
    {"role":"user","content":"That’s a good start, but the initial response wasn’t helpful. Could you specifically tell me which programs at the University of Amsterdam emphasize courses similar to the ones I enjoyed during my bachelor’s degree – specifically data structures, algorithms, data mining, and artificial intelligence?"}],
  "last_response_of_session":false, 
  "last_response_of_run":false
}
```

#### 3. Switching Topics

There is no way to manually end the current conversation and move on to the next topic. The (simulated) user is responsible for that decision. This decision is indicated by the flag `last_response_of_session`. If this flag is true, the next call to the `/run/continue` endpoint will result in the initial user utterance for the next topic. 

**Important**: If participants provide a response at the turn after this flag becomes true, this response will be ignored. The `response` field can be an empty string or `null` in this case.

#### 4. Finishing a Run

When the (simulated) users inquired about all topics in the dataset, the flag `last_response_of_run` will become true. This indicates that the run is done. Further requests after this flag becomes true will lead to errors.

#### Limits

Participants can submit a limited number of runs. Incomplete runs will be evaluated as well. Missing topics will be assessed with a performance of zero.   

### Debugging / Testing a System

Participants can also use the API for debugging and testing their systems. To this end, there are equivalent endpoints that emulate a run submission. 

* `localhost:8888/simulation/debug/start`
* `localhost:8888/simulation/debug/continue`

These two endpoints expect the exact same inputs as their run submission counterparts. 

**Important:** Responses submitted to the debugging endpoints will not be evaluated. 

#### Budget for Requests

Participants are allowed a limited number of requests for the debugging of their systems. The exact number of requests is to be determined. 

To keep track of the available budget, participants can check their available credits with the following request. 

```shell
curl -H "Authorization: Bearer <token>" "localhost:8888/simulation/budget/check" 
```



### Monitor Submission Progress

#### Check Run Status

Participants can check the status of their runs to make sure that everything worked as expected. The following request can be used to check the status.

```shell
curl -X GET -H "Authorization: Bearer <token>" "localhost:8888/simulation/run/status?run_id=teamA-llama3-dense-retrieval"
```

A typical response looks like the following.

```json
{
  "status": "complete",
  "open_topics": [],
  "done_topics": [...]
}
```

Responses contain the following fields:
* `status`: There are three possible values for status:
  * `active`: The requested run is currently being worked on and is not complete yet.
  * `completed`: The requested run is done and was submitted successfully.
  * `inactive`: The run was not completed but (due to an error) the run is currently not active. This can only happen if the server crashes. The run can be worked on as usual which will push the run back into the `active` state.
* `open_topics`: A list of topic ids that still need to be worked on to reach the `complete` status.
* `done_topics`: A list of topic ids of topics that were already completed in this run. 

#### Dump Run File

For your own documentation you can get a copy of the run submission file. 

**Important:** You don't have to submit this file anywhere. This file is just for your own reference.

To produce the run file you can run the following command:

```shell
curl -H "Authorization: Bearer <token>" "localhost:8888/run/dump?run_id=teamA-llama3-dense-retrieval"
```

As a response, you will receive the run file in the submission format for this task.

```json
[
  {
    "metadata": {
      "team_id": "teamA",
      "run_id": "teamA-llama3-dense-retrieval",
      "type": "interactive",
      "description": "The approach uses a retrieval-augmented generation pipeline with llama3.3 70B as generation backbone and a dense retrieval approach for the retrieval of relevant passages.",
      "track_persona": 0,
      "topic_id": "1-1_0"
    },
    "responses": [
      {
        "rank": 1,
        "user_utterance": "Okay, let’s start with a list of elite universities in Canada.",
        "text": "I don't know.",
        "citations": {},
        "ptkb_provenance": []
      }
    ],
    "references": {}
  },
  {
     "metadata": {
      "team_id": "teamA",
      "run_id": "teamA-llama3-dense-retrieval",
      "type": "interactive",
      "description": "The approach uses a retrieval-augmented generation pipeline with llama3.3 70B as generation backbone and a dense retrieval approach for the retrieval of relevant passages.",
      "track_persona": 0,
      "topic_id": "1-1_1"
    },
    "responses": [
      {
        "rank": 1,
        "user_utterance": "Specifically, which elite universities exist in Canada that might be suitable for a Computer Science graduate from the Netherlands, considering my preference for moderate climates and lack of a driver's license?",
        "text": "I don't know.",
        "citations": {},
        "ptkb_provenance": []
      }
    ],
    "references": {}
  },
  ...
]
```

### Support

In case of technical issues or other form of feedback, feel free to contact [marcel.gohsen@uni-weimar.de](mailto:marcel.gohsen@uni-weimar.de). 
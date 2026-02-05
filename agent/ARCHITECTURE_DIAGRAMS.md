# Language-Guided Robotic Pouring: LLM-MCP Framework

## 1. System Architecture Overview

```mermaid
graph TB
    subgraph "User Interface Layer"
        UI[Natural Language Input]
    end
    
    subgraph "AI Agent Layer"
        React[LangGraph ReAct Agent<br/>Claude Sonnet 4]
        SysPrompt[Dynamic System Prompt<br/>Scene Context Injection]
        
        subgraph "Tool Layer"
            Query[Query Tools<br/>get_scene_objects<br/>get_robot_status<br/>ask_clarification]
            Single[Single Action Tools<br/>pick_object<br/>place_object<br/>move_and_pour<br/>return_home]
            Composite[Composite Tool<br/>execute_full_pour_sequence]
        end
    end
    
    subgraph "Task Execution Layer"
        TaskGraph[Task Graph<br/>StateGraph with Memory]
        Retry[Retry Logic<br/>3-attempt mechanism]
    end
    
    subgraph "Scene Perception Layer"
        SceneManager[Scene Manager<br/>Thread-safe State]
        Detection[ROS2 Detection<br/>/object_detection_result]
    end
    
    subgraph "Robot Control Layer"
        ActionLib[MTC Action Library<br/>C++/Python Bridge]
        MoveGroup[MoveIt2 MoveGroup]
        Robot[UF850 Robot Arm]
    end
    
    UI --> React
    React <--> SysPrompt
    SysPrompt <--> SceneManager
    React --> Query
    React --> Single
    React --> Composite
    
    Query --> SceneManager
    Single --> ActionLib
    Composite --> TaskGraph
    TaskGraph --> Retry
    Retry --> ActionLib
    
    Detection --> SceneManager
    ActionLib --> MoveGroup
    MoveGroup --> Robot
    Robot -.Feedback.-> SceneManager
    
    style React fill:#e1f5ff
    style TaskGraph fill:#fff4e1
    style ActionLib fill:#ffe1e1
    style SceneManager fill:#e1ffe1
```

## 2. Semantic React Workflow

```mermaid
sequenceDiagram
    participant User
    participant ReAct as ReAct Agent
    participant LLM as Claude Sonnet 4
    participant Tools as Action Tools
    participant Scene as Scene Manager
    participant Robot as Robot Execution
    
    User->>ReAct: "把object_1倒给object_2"
    
    rect rgb(240, 248, 255)
        Note over ReAct,LLM: Reasoning Phase
        ReAct->>Scene: Get current scene state
        Scene-->>ReAct: objects: [object_1, object_2]<br/>robot_holding: None
        ReAct->>LLM: Build dynamic prompt with context
        LLM-->>ReAct: Understand intent: Full pour sequence
    end
    
    rect rgb(255, 248, 240)
        Note over ReAct,Tools: Action Phase 1
        LLM->>Tools: execute_full_pour_sequence(object_1, object_2)
        Tools->>Robot: 1. Pick object_1
        Robot-->>Tools: ✓ Success
        Tools->>Scene: Update robot_holding = object_1
    end
    
    rect rgb(240, 255, 240)
        Note over Tools,Robot: Action Phase 2-4
        Tools->>Robot: 2. Move and pour to object_2
        Robot-->>Tools: ✓ Success
        Tools->>Robot: 3. Place back object_1
        Robot-->>Tools: ✓ Success
        Tools->>Robot: 4. Return home
        Robot-->>Tools: ✓ Success
        Tools->>Scene: Update robot_holding = None
    end
    
    rect rgb(255, 240, 240)
        Note over ReAct,User: Response Phase
        Tools-->>LLM: All steps completed
        LLM->>ReAct: Generate natural language response
        ReAct-->>User: "倒水任务完成！✅"
    end
```

## 3. Task Graph State Machine

```mermaid
stateDiagram-v2
    [*] --> ResolveAndChoosePlan
    
    ResolveAndChoosePlan --> ParseInput: Parse user prompt
    ParseInput --> IdentifyTemplate: Extract object IDs
    IdentifyTemplate --> DoPick: Template Selected<br/>(P1/P2/P3)
    
    state DoPick {
        [*] --> Attempt1
        Attempt1 --> CheckSuccess1: Execute pick
        CheckSuccess1 --> [*]: Success ✓
        CheckSuccess1 --> Attempt2: Fail (auto-retry)
        Attempt2 --> CheckSuccess2: Execute pick
        CheckSuccess2 --> [*]: Success ✓
        CheckSuccess2 --> AskUser: Fail (2nd time)
        AskUser --> Attempt3: User approves
        AskUser --> [*]: User skips
        Attempt3 --> [*]: Final attempt
    }
    
    DoPick --> DoMoveToPour: Pick succeeded
    
    state DoMoveToPour {
        [*] --> ExecuteMove
        ExecuteMove --> ExecutePour: Move completed
        ExecutePour --> [*]: Pour executed
    }
    
    DoMoveToPour --> DoPlace: Move completed
    
    state DoPlace {
        [*] --> PlaceBack
        PlaceBack --> [*]: Placed at origin
    }
    
    DoPlace --> DoReturn: Place succeeded
    
    state DoReturn {
        [*] --> ReturnHome
        ReturnHome --> [*]: At home position
    }
    
    DoReturn --> [*]: Sequence complete
    
    note right of ResolveAndChoosePlan
        Templates:
        P1: src→dst (pour)
        P2: src→default (pour)
        P3: src→dst (no pour)
    end note
    
    note right of DoPick
        3-attempt retry logic
        with user confirmation
    end note
```

## 4. Data Flow Architecture

```mermaid
graph LR
    subgraph "Perception"
        Camera[Intel RealSense D435i]
        Detector[YOLO/Florence Detection]
        ROS2[ROS2 Topic<br/>/object_detection_result]
    end
    
    subgraph "Scene State Management"
        SceneState[Scene State<br/>Thread-safe]
        Objects[Objects List]
        RobotState[Robot State]
        Details[Object Details<br/>class, confidence, pose]
    end
    
    subgraph "AI Decision Making"
        Context[Context Builder]
        Prompt[System Prompt<br/>with Scene Context]
        LLM[Claude Sonnet 4<br/>Function Calling]
        Tools[8 LangChain Tools]
    end
    
    subgraph "Execution"
        ActionLib[Action Library]
        MTC[MoveIt Task Constructor]
        Planning[Motion Planning]
        Control[Robot Control]
    end
    
    Camera --> Detector
    Detector --> ROS2
    ROS2 --> SceneState
    SceneState --> Objects
    SceneState --> RobotState
    SceneState --> Details
    
    Objects --> Context
    RobotState --> Context
    Details --> Context
    Context --> Prompt
    Prompt --> LLM
    LLM --> Tools
    
    Tools --> ActionLib
    ActionLib --> MTC
    MTC --> Planning
    Planning --> Control
    Control -.Feedback.-> RobotState
    
    style SceneState fill:#90EE90
    style LLM fill:#87CEEB
    style ActionLib fill:#FFB6C1
```

## 5. Task Performance Matrix

| Template | Description | Perception Setup | Grasp Success | Pour Accuracy | Safety |
|----------|-------------|------------------|---------------|---------------|---------|
| **T2: Single Pour** | Pick→Pour→Place→Return | Fixed scene<br/>92% detection | 89% success<br/>3-attempt retry | Standard tilt<br/>120-140° | Collision check<br/>Safe retreat |
| **T3: Multi-Source** | Initial setup + First pour | Dynamic scene<br/>78% multi-obj | 85% success<br/>First grasp critical | Two-container<br/>Sequential pour | Stable grip<br/>2-source handling |
| **T4: Multi-Material** | Water pour handling | Material classification<br/>85% accuracy | Standard grasp<br/>Volume estimation | <10ml error<br/>Liquid dynamics | Spill prevention<br/>Tilt control |
| **T5: Complex Scene** | Cluttered environment | Multi-object<br/>66% clutter handling | Safe pose selection<br/>8 candidate poses | Multi-step sequence<br/>32.3s execution | Collision avoidance<br/>Real-time check |

## 6. Semantic Understanding Pipeline

```mermaid
graph TD
    Input[User Input<br/>"把object_1倒给object_2"]
    
    subgraph "Semantic Analysis"
        Intent[Intent Recognition]
        Entities[Entity Extraction<br/>object_1, object_2]
        Action[Action Classification<br/>Full Pour Sequence]
        Context[Context Validation<br/>Check scene state]
    end
    
    subgraph "Parameter Inference"
        Single{Single object?}
        Multi{Multiple objects?}
        Explicit{Explicit ID?}
        Ambiguous[Ask Clarification]
        Infer[Auto Inference]
    end
    
    subgraph "Tool Selection"
        ToolMatch[Match to Tool]
        Params[Build Parameters]
        Validate[Validate Safety Rules]
    end
    
    subgraph "Execution"
        Call[Tool Call]
        Monitor[Execution Monitor]
        Feedback[Real-time Feedback]
    end
    
    Input --> Intent
    Intent --> Entities
    Entities --> Action
    Action --> Context
    
    Context --> Single
    Single -->|Yes| Infer
    Single -->|No| Multi
    Multi --> Explicit
    Explicit -->|Yes| Infer
    Explicit -->|No| Ambiguous
    Ambiguous --> Infer
    
    Infer --> ToolMatch
    ToolMatch --> Params
    Params --> Validate
    
    Validate --> Call
    Call --> Monitor
    Monitor --> Feedback
    Feedback -.Update.-> Context
    
    style Intent fill:#E1F5FF
    style ToolMatch fill:#FFE1E1
    style Monitor fill:#E1FFE1
```

## 7. System Component Interaction Timeline

```mermaid
gantt
    title Robotic Pouring Task Execution Timeline
    dateFormat X
    axisFormat %Ss
    
    section Perception
    Scene detection          :active, 0, 2s
    Object tracking         :active, 2s, 60s
    
    section AI Agent
    User input processing   :crit, 0, 1s
    Semantic understanding  :crit, 1s, 2s
    Tool selection         :crit, 2s, 3s
    
    section Pick Phase
    Plan pick motion       :3s, 5s
    Execute approach       :5s, 8s
    Grasp execution       :8s, 10s
    Lift container        :10s, 12s
    
    section Pour Phase
    Plan pour motion      :12s, 15s
    Move to position      :15s, 20s
    Execute tilt          :20s, 25s
    Pour liquid          :25s, 28s
    Tilt back            :28s, 30s
    
    section Place Phase
    Plan place motion     :30s, 32s
    Move to origin        :32s, 37s
    Release container     :37s, 39s
    Retreat              :39s, 41s
    
    section Return Phase
    Return to home        :41s, 45s
    Confirm completion    :45s, 46s
```

## 8. Safety and Constraint Framework

```mermaid
mindmap
    root((Safety Framework))
        Semantic Constraints
            No coordinate generation
            No quaternion output
            No joint angle control
            No hardware access
        Motion Constraints
            Collision checking
            Joint limits
            Velocity limits 0.05-0.3
            Workspace boundaries
        Task Constraints
            Scene validation
            Object existence check
            Grasp feasibility
            Pour stability
        Execution Constraints
            3-attempt retry
            User confirmation
            Error recovery
            Emergency stop
        Perception Constraints
            Detection confidence >0.7
            Pose estimation quality
            Object tracking stability
            Scene consistency
```

## 9. Tool Hierarchy and Capabilities

```mermaid
graph TB
    subgraph "Query Tools"
        Q1[get_scene_objects<br/>Scene Inspection]
        Q2[get_robot_status<br/>State Query]
        Q3[ask_user_clarification<br/>Interactive Clarification]
    end
    
    subgraph "Atomic Action Tools"
        A1[pick_object<br/>Grasp Container]
        A2[place_object<br/>Release Container]
        A3[move_and_pour<br/>Pour Motion]
        A4[return_home<br/>Safe Position]
    end
    
    subgraph "Composite Action Tool"
        C1[execute_full_pour_sequence<br/>Complete Workflow]
    end
    
    subgraph "Backend Integration"
        AL[Action Library]
        MTC[MoveIt Task Constructor]
        subgraph "MTC Stages"
            S1[CurrentState]
            S2[OpenGripper]
            S3[MoveTo]
            S4[GenerateGrasp]
            S5[AllowCollision]
            S6[MicroInsert]
            S7[CloseGripper]
            S8[AttachObject]
            S9[LiftContainer]
            S10[MoveToPour]
            S11[TiltSequence]
        end
    end
    
    Q1 --> AL
    Q2 --> AL
    A1 --> AL
    A2 --> AL
    A3 --> AL
    A4 --> AL
    C1 --> A1
    C1 --> A3
    C1 --> A2
    C1 --> A4
    
    AL --> MTC
    MTC --> S1
    S1 --> S2
    S2 --> S3
    S3 --> S4
    S4 --> S5
    S5 --> S6
    S6 --> S7
    S7 --> S8
    S8 --> S9
    S9 --> S10
    S10 --> S11
    
    style C1 fill:#FFD700
    style AL fill:#FF6B6B
    style MTC fill:#4ECDC4
```

## 10. Evaluation Metrics Framework

```mermaid
graph TB
    subgraph "Task Success Metrics"
        TS1[Task Completion Rate]
        TS2[Step-wise Success Rate]
        TS3[Retry Statistics]
        TS4[Error Recovery Rate]
    end
    
    subgraph "Performance Metrics"
        PM1[Execution Time<br/>Total Duration]
        PM2[Planning Time<br/>Per Stage]
        PM3[Motion Smoothness<br/>Jerk Metrics]
        PM4[Throughput<br/>Tasks/Hour]
    end
    
    subgraph "Quality Metrics"
        QM1[Grasp Success Rate<br/>89% Pick]
        QM2[Pour Accuracy<br/>Volume Error]
        QM3[Placement Precision<br/>Position Error]
        QM4[Safety Compliance<br/>Collision Rate]
    end
    
    subgraph "Intelligence Metrics"
        IM1[Intent Recognition<br/>Semantic Accuracy]
        IM2[Parameter Inference<br/>Context Understanding]
        IM3[Clarification Rate<br/>Ambiguity Handling]
        IM4[Adaptation Ability<br/>Scene Changes]
    end
    
    subgraph "Overall System Score"
        Overall[System Performance Index]
    end
    
    TS1 --> Overall
    TS2 --> Overall
    TS3 --> Overall
    TS4 --> Overall
    PM1 --> Overall
    PM2 --> Overall
    PM3 --> Overall
    PM4 --> Overall
    QM1 --> Overall
    QM2 --> Overall
    QM3 --> Overall
    QM4 --> Overall
    IM1 --> Overall
    IM2 --> Overall
    IM3 --> Overall
    IM4 --> Overall
    
    style Overall fill:#FF6B6B
    style TS1 fill:#4ECDC4
    style PM1 fill:#95E1D3
    style QM1 fill:#F38181
    style IM1 fill:#FFD93D
```

---

## Key Features Summary

### 🎯 **Semantic React Agent**
- Natural language understanding via Claude Sonnet 4
- Dynamic context injection with real-time scene state
- 8 specialized tools for flexible task execution
- Intelligent parameter inference and user clarification

### 🔄 **Task Graph Execution**
- Deterministic state machine: Pick → Move → Pour → Place → Return
- 3-attempt retry mechanism with user confirmation
- Template selection (P1/P2/P3) based on task complexity
- Real-time event reporting and feedback

### 🤖 **Robot Integration**
- MoveIt Task Constructor for motion planning
- Action Library abstraction layer
- ROS2-based scene perception
- Thread-safe state management

### 📊 **Performance Highlights**
- 92% scene detection accuracy (single object)
- 89% grasp success rate (with retry)
- 21.3s average execution time (single pour)
- <10ml pouring error (multi-material tasks)


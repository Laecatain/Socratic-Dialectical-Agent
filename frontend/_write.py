import os
path = r"E:\app\Socratic Dialectical Agent\frontend\src\App.tsx"
with open(path, "w", encoding="utf-8") as f:
    f.write("""import { useSocraticStream } from './hooks/useSocraticStream';
import Sidebar from './components/Sidebar';
import DialogueArea from './components/DialogueArea';
import './App.css';

function App() {
  const {
    agentState,
    isThinking,
    nodeProgress,
    currentNode,
    askSocrates,
    reset,
    cancel,
  } = useSocraticStream();

  return (
    <div className="app-container">
      <Sidebar
        agentState={agentState}
        nodeProgress={nodeProgress}
        currentNode={currentNode}
        isThinking={isThinking}
      />
      <DialogueArea
        agentState={agentState}
        isThinking={isThinking}
        currentNode={currentNode}
        askSocrates={askSocrates}
        reset={reset}
        cancel={cancel}
      />
    </div>
  );
}

export default App;
""")
print("Done")

import { Sidebar } from '../../components/Sidebar';

function App() {
  const [isCollapsed, setIsCollapsed] = useState(false);

  return (
    <div className="flex min-h-screen bg-[#f8f4fb] text-slate-800 font-sans">
      <Sidebar isCollapsed={isCollapsed} setIsCollapsed={setIsCollapsed} />
      <main className="flex-1 p-8 text-center">
        <h1 className="text-2xl font-bold mb-4">CruzBuy Assistant Home Page</h1>
      </main>
    </div>
  );
}

export default App;
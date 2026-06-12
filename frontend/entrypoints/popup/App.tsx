import { Sidebar } from '../../components/Sidebar';

function App() {
  const [isCollapsed, setIsCollapsed] = useState(false);

  const handleOpenNewTab = () => {
    browser.tabs.create({ 
      url: browser.runtime.getURL('/home.html') 
    });
  };

  return (
    <div className="flex h-[600px] w-[500px] overflow-hidden bg-[#f8f4fb] text-slate-800 font-sans">
      <Sidebar isCollapsed={isCollapsed} setIsCollapsed={setIsCollapsed} onOpenNewTab={handleOpenNewTab} />
      <main className="flex-1 p-4 overflow-y-auto">
        <div className="text-sm text-gray-400 italic text-center mt-10">
          Welcome to CruzBuy Assistant
        </div >
      </main>
    </div>
  );
}

export default App;

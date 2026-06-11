import { Sidebar } from '../../components/Sidebar';

function App() {
  const [isCollapsed, setIsCollapsed] = useState(false);

  const handleOpenNewTab = () => {
    browser.tabs.create({ 
      url: browser.runtime.getURL('/home.html') 
    });
  };

  return (
    <div className="flex h-[500px] w-[400px] overflow-hidden bg-[#f8f4fb] text-slate-800 font-sans">
      <Sidebar isCollapsed={isCollapsed} setIsCollapsed={setIsCollapsed} onOpenNewTab={handleOpenNewTab} />
      <main className="flex-1 p-4 overflow-y-auto">
        <div className="text-sm text-gray-400 italic text-center mt-10">
          Main content area
        </div >
      </main>
    </div>
  );
}

export default App;

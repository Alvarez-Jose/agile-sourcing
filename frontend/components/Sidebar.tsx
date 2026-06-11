interface SidebarProps {
  isCollapsed: boolean;
  setIsCollapsed: (collapsed: boolean) => void;
  onOpenNewTab?: () => void;
}

export function Sidebar({ isCollapsed, setIsCollapsed, onOpenNewTab }: SidebarProps) {
  return (
    <aside className={`flex flex-col justify-between border-r border-gray-200 bg-white shadow-sm transition-all duration-300 ${isCollapsed ? 'w-12' : 'w-32'}`}>
      <div className="p-1 flex flex-col gap-2 items-center">
        <button
          onClick={() => setIsCollapsed(!isCollapsed)}
          className={`flex items-center justify-center transition-all duration-300 rounded-md hover:bg-gray-100 cursor-pointer ${isCollapsed ? 'w-10 h-10' : 'w-full p-2 text-gray-500'}`}
        >
          <svg
            xmlns="http://www.w3.org/2000/svg"
            fill="none"
            viewBox="0 0 24 24"
            stroke="currentColor"
            className="size-5"
          >
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d={isCollapsed ? "M12 19l7-7 -7-7m-8 14l7-7 -7-7" : "M15 19l-7-7 7-7"} />
          </svg>
        </button>

        <button
          onClick={() => console.log('Start chat clicked')}
          className={`flex ${isCollapsed ? 'flex-col' : 'flex-row items-center'} items-center justify-center transition-all duration/300 rounded-md bg-[#00539b] hover:bg-[#003d6f] active:scale-95 cursor-pointer text-white ${isCollapsed ? 'w-10 h-10' : 'w-full p-2 text-xs font-semibold'}`}
        >
          <svg 
            xmlns="http://www.w3.org/2000/svg"
            fill="none"
            viewBox="0 0 24 24"
            stroke="currentColor"
            aria-hidden="true"
            strokeWidth="1.5"
            className={isCollapsed ? "size-5" : "size-5 mr-2"}
          >
            <path strokeLinecap="round" strokeLinejoin="round" d="m16.862 4.487 1.687-1.688a1.875 1.875 0 1 1 2.652 2.652L10.582 16.07a4.5 4.5 0 0 1-1.897 1.13L6 18l.8-2.685a4.5 4.5 0 0 1 1.13-1.897l8.932-8.931Zm0 0L19.5 7.125M18 14v4.75A2.25 2.25 0 0 1 15.75 21H5.25A2.25 2.25 0 0 1 3 18.75V8.25A2.25 2.25 0 0 1 5.25 6H10" />
          </svg>
          {!isCollapsed && <span className="whitespace-nowrap">Start Chat</span>}
        </button>
      </div>

      {onOpenNewTab && (
        <div className="p-1 border-t border-gray-100 flex flex-col items-center">
          <button
            onClick={onOpenNewTab}
            className={`flex ${isCollapsed ? 'flex-col' : 'flex-row items-center'} items-center justify-center transition-all duration-300 rounded-md hover:bg-gray-100 hover:text-[#00539b] active:scale-95 cursor-pointer ${isCollapsed ? 'w-10 h-10' : 'w-full p-2 text-[10px] font-medium text-gray-600'}`}
          >
            <svg
              xmlns="http://www.w3.org/2000/svg"
              viewBox="0 0 24 24"
              fill="currentColor" 
              stroke="currentColor" 
              strokeWidth="1" 
              strokeLinecap="round" 
              strokeLinejoin="round" 
              className={isCollapsed ? "size-5" : "size-5 mr-2"}
            >
              <path d="M 5 3 C 3.9069372 3 3 3.9069372 3 5 L 3 19 C 3 20.093063 3.9069372 21 5 21 L 19 21 C 20.09 21 21 20.093063 21 19 L 21 12 L 19 12 L 19 19 L 5 19 L 5 5 L 12 5 L 12 3 L 5 3 z M 14 3 L 14 5 L 17.585938 5 L 8.2929688 14.292969 L 9.7070312 15.707031 L 19 6.4140625 L 19 10 L 21 10 L 21 3 L 14 3 z"></path>
            </svg>
            {!isCollapsed && <span className="whitespace-nowrap">Open Webpage</span>}
          </button>
        </div>
      )}
    </aside>
  );
}


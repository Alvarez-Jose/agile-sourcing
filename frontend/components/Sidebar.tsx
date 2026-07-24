import { Link } from 'react-router-dom';
import Login from './pages/Login';

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

        <Link
          to="/chat.html"
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
        </Link>
        <Login />
      </div>

        <div className="p-1 border-t border-gray-100 flex flex-col items-center">
          <Link
            to="/settings.html"
            className={` group flex ${isCollapsed ? 'flex-col' : 'flex-row items-center'} items-center justify-center transition-all duration-300 rounded-md hover:bg-gray-100 hover:text-[#00539b] active:scale-95 cursor-pointer ${isCollapsed ? 'w-10 h-10' : 'w-full p-2 text-[10px] font-medium text-gray-600'}`}
          >
            <svg xmlns="http://www.w3.org/2000/svg"
              viewBox="0 0 24 24"
              fill="currentColor" 
              stroke="currentColor" 
              strokeWidth="1" 
              strokeLinecap="round" 
              strokeLinejoin="round" 
              className={`${isCollapsed ? "size-5" : "size-5 mr-2"} group-hover:animate-[spin_2s_linear_infinite]`}
            >
              <path d="M 10.490234 2 C 10.011234 2 9.6017656 2.3385938 9.5097656 2.8085938 L 9.1757812 4.5234375 C 8.3550224 4.8338012 7.5961042 5.2674041 6.9296875 5.8144531 L 5.2851562 5.2480469 C 4.8321563 5.0920469 4.33375 5.2793594 4.09375 5.6933594 L 2.5859375 8.3066406 C 2.3469375 8.7216406 2.4339219 9.2485 2.7949219 9.5625 L 4.1132812 10.708984 C 4.0447181 11.130337 4 11.559284 4 12 C 4 12.440716 4.0447181 12.869663 4.1132812 13.291016 L 2.7949219 14.4375 C 2.4339219 14.7515 2.3469375 15.278359 2.5859375 15.693359 L 4.09375 18.306641 C 4.33275 18.721641 4.8321562 18.908906 5.2851562 18.753906 L 6.9296875 18.1875 C 7.5958842 18.734206 8.3553934 19.166339 9.1757812 19.476562 L 9.5097656 21.191406 C 9.6017656 21.661406 10.011234 22 10.490234 22 L 13.509766 22 C 13.988766 22 14.398234 21.661406 14.490234 21.191406 L 14.824219 19.476562 C 15.644978 19.166199 16.403896 18.732596 17.070312 18.185547 L 18.714844 18.751953 C 19.167844 18.907953 19.66625 18.721641 19.90625 18.306641 L 21.414062 15.691406 C 21.653063 15.276406 21.566078 14.7515 21.205078 14.4375 L 19.886719 13.291016 C 19.955282 12.869663 20 12.440716 20 12 C 20 11.559284 19.955282 11.130337 19.886719 10.708984 L 21.205078 9.5625 C 21.566078 9.2485 21.653063 8.7216406 21.414062 8.3066406 L 19.90625 5.6933594 C 19.66725 5.2783594 19.167844 5.0910937 18.714844 5.2460938 L 17.070312 5.8125 C 16.404116 5.2657937 15.644607 4.8336609 14.824219 4.5234375 L 14.490234 2.8085938 C 14.398234 2.3385937 13.988766 2 13.509766 2 L 10.490234 2 z M 12 8 C 14.209 8 16 9.791 16 12 C 16 14.209 14.209 16 12 16 C 9.791 16 8 14.209 8 12 C 8 9.791 9.791 8 12 8 z"></path>
            </svg>
            {!isCollapsed && <span className="whitespace-nowrap">Settings</span>}
          </Link>
          {onOpenNewTab && (
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
          )}
        </div>
    </aside>
  );
}


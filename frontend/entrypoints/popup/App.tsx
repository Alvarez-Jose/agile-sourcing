function App() {
  return (
    <>
      <h1>Test</h1>
      <button
        onClick={() => browser.tabs.create({ 
          url: browser.runtime.getURL('/home.html') 
        })}
        className="mt-4 p-2 bg-blue-500 text-white rounded"
      ></button>
    </>
  );
}

export default App;

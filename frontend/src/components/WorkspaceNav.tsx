import { useEffect, useRef, useState } from "react";
import { ArrowDown, ArrowUp, ChevronRight, Command, CornerDownLeft, Database, Layers3, Menu, Radio, Search, X } from "lucide-react";
import { pages, type Page, type PageId } from "../pages";

type Props = {
  page: Page;
  navigate: (id: PageId) => void;
  apiConnected: boolean;
  runCount: number;
};

function Brand() {
  return <div className="brand">
    <span className="brand-icon" aria-hidden="true"><Radio size={25} strokeWidth={2.1}/></span>
    <span><strong>MOBI-HO <em>Lab</em></strong><small>AIORI-3 / PS-016</small></span>
  </div>;
}

export default function WorkspaceNav({ page, navigate, apiConnected, runCount }: Props) {
  const dialog = useRef<HTMLDialogElement>(null);
  const search = useRef<HTMLInputElement>(null);
  const [query, setQuery] = useState("");
  const [cursor, setCursor] = useState(0);
  const results = pages.filter(p => (p.name + " " + p.group + " " + p.title).toLowerCase().includes(query.trim().toLowerCase()));

  function openSearch() {
    if (dialog.current?.open) return;
    setQuery("");
    setCursor(0);
    dialog.current?.showModal();
    search.current?.focus();
  }

  function choose(id: PageId) {
    dialog.current?.close();
    navigate(id);
  }

  useEffect(() => {
    const onShortcut = (event: KeyboardEvent) => {
      if ((event.metaKey || event.ctrlKey) && event.key.toLowerCase() === "k") {
        event.preventDefault();
        if (dialog.current?.open) dialog.current.close();
        else openSearch();
      }
    };
    window.addEventListener("keydown", onShortcut);
    return () => window.removeEventListener("keydown", onShortcut);
  }, []);

  return <>
    <a href="#workspace-content" className="skip-link" onClick={event => {
      event.preventDefault();
      document.getElementById("workspace-content")?.focus();
    }}>Skip to content</a>
    <aside className="sidebar">
      <Brand/>
      <nav aria-label="Lab workspace">
        {["Workspace", "Analysis", "Execution"].map(group => <div className="nav-group" key={group}>
          <p>{group}</p>
          {pages.filter(item => item.group === group).map(({ id, name, Icon }) =>
            <a href={`#${id}`} key={id} aria-label={name} title={name} className={`nav-item ${page.id === id ? "selected" : ""}`}
              onClick={event => { event.preventDefault(); navigate(id); }}
              aria-current={page.id === id ? "page" : undefined}>
              <Icon size={17}/><span>{name}</span>
            </a>)}
        </div>)}
      </nav>
      <div className="sidebar-bottom">
        <div className="archive-icon"><Database size={17}/></div>
        <div><strong>Benchmark archive</strong><small>{runCount} recorded runs</small></div>
      </div>
    </aside>
    <header className="topbar">
      <button className="mobile-menu icon-button" aria-label="Open navigation" onClick={openSearch}><Menu size={20}/></button>
      <div className="breadcrumb"><Layers3 size={16}/><span>{page.group}</span><ChevronRight size={13}/><strong>{page.name}</strong></div>
      <div className="top-right">
        <button className="page-search" onClick={openSearch} aria-label="Search pages">
          <Search size={15}/><span>Search pages</span><kbd>{/Mac|iPhone|iPad/.test(navigator.platform) ? "⌘" : "Ctrl"} K</kbd>
        </button>
        <span className="source-status"><i/>{apiConnected ? "API connected" : "Recorded mode"}</span>
      </div>
    </header>
    <dialog className="page-dialog" ref={dialog} aria-labelledby="page-picker-title"
      onClick={event => { if (event.target === event.currentTarget) dialog.current?.close(); }}>
      <div className="picker-inner">
        <h2 id="page-picker-title" className="sr-only">Search dashboard pages</h2>
        <div className="picker-input"><Search size={19}/>
          <input ref={search} value={query} onChange={event => { setQuery(event.target.value); setCursor(0); }}
            aria-label="Search dashboard pages" placeholder="Find a page…" autoComplete="off"
            role="combobox" aria-controls="picker-results" aria-expanded={true}
            aria-activedescendant={results[cursor] ? `picker-${results[cursor].id}` : undefined}
            onKeyDown={event => {
              if (!results.length) return;
              if (event.key === "ArrowDown" || event.key === "ArrowUp") {
                event.preventDefault();
                const step = event.key === "ArrowDown" ? 1 : -1;
                const next = (cursor + step + results.length) % results.length;
                setCursor(next);
                document.getElementById(`picker-${results[next].id}`)?.scrollIntoView({ block: "nearest" });
              } else if (event.key === "Enter") { event.preventDefault(); choose(results[cursor].id); }
            }}/>
          <button className="icon-button" onClick={() => dialog.current?.close()} aria-label="Close page search"><X size={17}/></button>
        </div>
        <div className="picker-results" role="listbox" aria-label="Pages" id="picker-results">
          {results.map((item, i) => <button id={`picker-${item.id}`} role="option" aria-selected={i === cursor}
            tabIndex={-1} className={i === cursor ? "current" : ""} key={item.id}
            onPointerMove={() => setCursor(i)} onClick={() => choose(item.id)}>
            <item.Icon size={17}/><strong>{item.name}</strong><small>{item.group}</small>
          </button>)}
        </div>
        {!results.length && <p className="empty-state" role="status">No pages match “{query}”.</p>}
        <div className="picker-hint"><Command size={13}/><span><ArrowUp size={12}/><ArrowDown size={12}/> Navigate</span><span><CornerDownLeft size={12}/> Open</span></div>
      </div>
    </dialog>
  </>;
}

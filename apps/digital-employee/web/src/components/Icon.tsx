export function Icon({name, size=20}: {name:'chevron'|'check'|'stop'|'arrow'|'workflow'|'history';size?:number}) {
const paths = {chevron:'m6 9 6 6 6-6',check:'m5 12 4 4L19 6',stop:'M7 7h10v10H7z',arrow:'M5 12h14m-6-6 6 6-6 6',workflow:'M12 3v5m0 0H5v7m7-7h7v7M9 3h6M3 15h4v5H3zm14 0h4v5h-4z',history:'M4 5v5h5M4 10a8 8 0 1 1 1 8M12 8v5l3 2'};
return <svg width={size} height={size} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true"><path d={paths[name]}/></svg>;
}

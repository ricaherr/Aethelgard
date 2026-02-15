import React, { useState } from 'react';
import { Info } from 'lucide-react';

interface InfoTooltipProps {
    title: string;
    content: string;
}

const InfoTooltip: React.FC<InfoTooltipProps> = ({ title, content }) => {
    const [isVisible, setIsVisible] = useState(false);

    return (
        <div className="relative inline-block ml-1">
            <button
                onMouseEnter={() => setIsVisible(true)}
                onMouseLeave={() => setIsVisible(false)}
                className="text-gray-500 hover:text-blue-400 transition-colors focus:outline-none"
            >
                <Info className="w-3 h-3" />
            </button>

            {isVisible && (
                <div className="absolute z-[100] w-64 p-3 mt-2 bg-gray-800 border border-gray-700 rounded-lg shadow-xl animate-in fade-in zoom-in duration-200">
                    <div className="flex items-center gap-2 mb-1 border-b border-gray-700 pb-1">
                        <Info className="w-3 h-3 text-blue-400" />
                        <span className="text-[10px] font-black uppercase tracking-widest text-white">{title}</span>
                    </div>
                    <p className="text-[11px] text-gray-400 leading-relaxed font-medium">
                        {content}
                    </p>
                </div>
            )}
        </div>
    );
};

export default InfoTooltip;

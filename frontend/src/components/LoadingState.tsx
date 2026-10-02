import React from 'react';
import { Loader2 } from 'lucide-react';

export interface LoadingStateProps {
  message?: string;
  className?: string;
}

export const LoadingState: React.FC<LoadingStateProps> = ({
  message = 'Memuat regulasi dari backend...',
  className = '',
}) => {
  return (
    <div className={`flex flex-col items-center justify-center p-12 text-center ${className}`}>
      <div className="p-3 bg-red-50 text-red-600 rounded-full mb-3 ring-8 ring-red-50/50">
        <Loader2 className="w-6 h-6 animate-spin text-red-600" />
      </div>
      <p className="text-sm font-semibold text-gray-800">{message}</p>
      <p className="text-xs text-gray-400 mt-1">Mohon tunggu sebentar, sistem sedang mengambil data.</p>
    </div>
  );
};

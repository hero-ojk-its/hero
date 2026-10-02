import React from 'react';
import { Search } from 'lucide-react';

export interface EmptyStateProps {
  title?: string;
  message?: string;
  onAction?: () => void;
  actionLabel?: string;
  className?: string;
}

export const EmptyState: React.FC<EmptyStateProps> = ({
  title = 'Tidak ada regulasi yang cocok',
  message = 'Coba sesuaikan kata kunci pencarian atau reset filter yang dipilih.',
  onAction,
  actionLabel = 'Reset Filter',
  className = '',
}) => {
  return (
    <div className={`flex flex-col items-center justify-center p-12 text-center my-4 ${className}`}>
      <div className="p-3 bg-gray-100 text-gray-500 rounded-full mb-3 ring-8 ring-gray-50">
        <Search className="w-6 h-6 text-gray-400" />
      </div>
      <h3 className="text-base font-bold text-gray-900 mb-1">{title}</h3>
      <p className="text-xs text-gray-500 max-w-sm mb-4 leading-relaxed">{message}</p>
      {onAction && (
        <button
          onClick={onAction}
          type="button"
          className="text-xs text-red-600 hover:text-red-700 font-semibold underline underline-offset-4 cursor-pointer"
        >
          {actionLabel}
        </button>
      )}
    </div>
  );
};

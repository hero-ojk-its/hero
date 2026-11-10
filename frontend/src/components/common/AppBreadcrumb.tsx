import { Link } from 'react-router-dom';

export interface BreadcrumbItem {
  label: string;
  to?: string;
  onClick?: () => void;
  title?: string;
  isCurrent?: boolean;
  variant?: 'default' | 'red';
}

export interface AppBreadcrumbProps {
  items: BreadcrumbItem[];
  includeDashboard?: boolean;
  className?: string;
}

export default function AppBreadcrumb({
  items,
  includeDashboard = true,
  className = '',
}: AppBreadcrumbProps) {
  // Prevent duplicate Dashboard if already provided as the first item
  const hasDashboardFirst =
    items.length > 0 &&
    (items[0].label.trim().toLowerCase() === 'dashboard' || items[0].to === '/');

  const resolvedItems: BreadcrumbItem[] =
    includeDashboard && !hasDashboardFirst
      ? [{ label: 'Dashboard', to: '/' }, ...items]
      : items;

  return (
    <nav
      aria-label="Breadcrumb"
      className={`flex items-center flex-wrap gap-y-1 text-xs font-medium ${className}`}
    >
      <ol className="flex items-center flex-wrap gap-y-1 list-none p-0 m-0">
        {resolvedItems.map((item, index) => {
          const isLast = index === resolvedItems.length - 1;
          const isCurrent = item.isCurrent ?? isLast;

          return (
            <li
              key={`${item.label}-${index}`}
              className="inline-flex items-center"
            >
              {index > 0 && (
                <span
                  className="mx-2 text-gray-300 select-none"
                  aria-hidden="true"
                >
                  /
                </span>
              )}
              {isCurrent ? (
                <span
                  aria-current="page"
                  className={
                    item.variant === 'red'
                      ? 'text-red-700 font-bold'
                      : 'text-gray-900 font-semibold cursor-default'
                  }
                  title={item.title}
                >
                  {item.label}
                </span>
              ) : item.onClick ? (
                <button
                  type="button"
                  onClick={item.onClick}
                  className="text-gray-500 hover:text-red-700 hover:underline transition-colors cursor-pointer bg-transparent border-0 p-0 text-xs font-medium focus:outline-none"
                  title={item.title}
                >
                  {item.label}
                </button>
              ) : item.to ? (
                <Link
                  to={item.to}
                  className="text-gray-500 hover:text-red-700 hover:underline transition-colors cursor-pointer"
                  title={item.title}
                >
                  {item.label}
                </Link>
              ) : (
                <span className="text-gray-500 cursor-default" title={item.title}>
                  {item.label}
                </span>
              )}
            </li>
          );
        })}
      </ol>
    </nav>
  );
}

export { AppBreadcrumb };

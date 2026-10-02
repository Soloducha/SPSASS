/** Entity actions component with edit/delete buttons and confirmation dialog. */

'use client';

import { Fragment, useState } from 'react';
import { Dialog, Transition } from '@headlessui/react';
import { PencilIcon, TrashIcon } from '@heroicons/react/24/outline';

interface EntityActionsProps {
  entityName: string;
  onEdit: () => void;
  onDelete: () => Promise<void>;
  isDeleting?: boolean;
  deleteLabel?: string;
  editLabel?: string;
}

export function EntityActions({
  entityName,
  onEdit,
  onDelete,
  isDeleting,
  deleteLabel = 'Eliminar',
  editLabel = 'Editar',
}: EntityActionsProps) {
  const [showDeleteDialog, setShowDeleteDialog] = useState(false);

  const handleDeleteClick = () => {
    setShowDeleteDialog(true);
  };

  const handleConfirmDelete = async () => {
    setShowDeleteDialog(false);
    await onDelete();
  };

  return (
    <Fragment>
      <div className="flex items-center gap-2">
        <button
          type="button"
          onClick={onEdit}
          disabled={isDeleting}
          className="p-2 rounded-md text-gray-500 hover:text-gray-700 hover:bg-gray-100 disabled:opacity-50 transition-colors"
          aria-label={editLabel}
        >
          <PencilIcon className="h-5 w-5" />
        </button>
        <button
          type="button"
          onClick={handleDeleteClick}
          disabled={isDeleting}
          className="p-2 rounded-md text-gray-500 hover:text-red-600 hover:bg-red-50 disabled:opacity-50 transition-colors"
          aria-label={deleteLabel}
        >
          <TrashIcon className="h-5 w-5" />
        </button>
      </div>

      <Transition.Root show={showDeleteDialog} as={Fragment}>
        <Dialog as="div" className="relative z-50" onClose={setShowDeleteDialog}>
          <Transition.Child
            as={Fragment}
            enter="ease-out duration-300"
            enterFrom="opacity-0"
            enterTo="opacity-100"
            leave="ease-in duration-200"
            leaveFrom="opacity-100"
            leaveTo="opacity-0"
          >
            <div className="fixed inset-0 bg-gray-900/25" />
          </Transition.Child>

          <div className="fixed inset-0 overflow-y-auto">
            <div className="flex min-h-full items-center justify-center p-4 text-center">
              <Transition.Child
                as={Fragment}
                enter="ease-out duration-300"
                enterFrom="opacity-0 scale-95"
                enterTo="opacity-100 scale-100"
                leave="ease-in duration-200"
                leaveFrom="opacity-100 scale-100"
                leaveTo="opacity-0 scale-95"
              >
                <Dialog.Panel className="w-full max-w-md transform overflow-hidden rounded-2xl bg-white p-6 text-left align-middle shadow-xl transition-all">
                  <Dialog.Title as="h3" className="text-lg font-semibold text-gray-900">
                    Confirmar eliminación
                  </Dialog.Title>
                  <div className="mt-2">
                    <p className="text-sm text-gray-500">
                      ¿Estás seguro de que quieres eliminar <strong>{entityName}</strong>? Esta acción no se puede deshacer.
                    </p>
                  </div>
                  <div className="mt-4 flex justify-end gap-3">
                    <button
                      type="button"
                      onClick={() => setShowDeleteDialog(false)}
                      disabled={isDeleting}
                      className="px-4 py-2 border border-gray-300 rounded-md text-sm font-medium text-gray-700 hover:bg-gray-50 disabled:opacity-50 transition-colors"
                    >
                      Cancelar
                    </button>
                    <button
                      type="button"
                      onClick={handleConfirmDelete}
                      disabled={isDeleting}
                      className="px-4 py-2 bg-red-600 border border-transparent rounded-md text-sm font-medium text-white hover:bg-red-700 disabled:opacity-50 transition-colors"
                    >
                      {isDeleting ? 'Eliminando...' : deleteLabel}
                    </button>
                  </div>
                </Dialog.Panel>
              </Transition.Child>
            </div>
          </div>
        </Dialog>
      </Transition.Root>
    </Fragment>
  );
}
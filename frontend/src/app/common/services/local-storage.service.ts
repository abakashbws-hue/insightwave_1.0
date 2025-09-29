import { Injectable, InjectionToken, Inject, Optional } from '@angular/core';
import { Subject } from 'rxjs';

/**
 * Injection token for providing a custom namespace for local storage.
 * If not provided, a default namespace 'app' will be used.
 *
 * @example
 * // in your app.config.ts or module providers:
 * // { provide: LOCAL_STORAGE_NAMESPACE, useValue: 'myUniqueAppNamespace' }
 */
export const LOCAL_STORAGE_NAMESPACE = new InjectionToken<string>('localStorageNamespace');

/**
 * Interface for the wrapper object used to store items along with metadata.
 * @template T The type of the data being stored.
 */
interface StorageItemWrapper<T> {
    payload: T;
    expiry?: number; // Expiration timestamp in milliseconds
}

/**
 * A robust local storage service for modern web applications.
 * It provides a namespaced, type-safe, and error-resilient API
 * for interacting with `window.localStorage`.
 *
 * Features:
 * - Uniform data handling (automatic JSON serialization/deserialization).
 * - Simple API (`get`, `set`, `remove`, `clearAll`).
 * - Robust error handling (quota exceeded, parsing errors, storage unavailability).
 * - Type safety with generics.
 * - Namespacing to prevent key collisions.
 * - Data expiration.
 * - Default values on retrieval.
 * - Periodic cleanup of expired items.
 */
@Injectable({
    providedIn: 'root',
})
export class LocalStorageService {
    private storage: Storage | null = null;
    private readonly namespacePrefix: string;
    private readonly currentNamespace: string;

    private itemExpiredSubject = new Subject<string>();
    public itemExpired$ = this.itemExpiredSubject.asObservable();

    constructor(@Optional() @Inject(LOCAL_STORAGE_NAMESPACE) namespace?: string) {
        this.currentNamespace = namespace || 'app';
        this.namespacePrefix = `${this.currentNamespace}:`;
        this.initializeStorage();
    }

    private initializeStorage(): void {
        try {
            // Check if localStorage is available and usable
            if (typeof window !== 'undefined' && window.localStorage) {
                this.storage = window.localStorage;
                const testKey = this.getNamespacedKey('__storage_test__');
                this.storage.setItem(testKey, 'test');
                this.storage.removeItem(testKey);
            } else {
                this.storage = null;
                console.warn('LocalStorageService: Local storage is not available in this environment.');
            }
        } catch (e) {
            console.warn('LocalStorageService: Local storage is disabled or not accessible (e.g., private browsing mode).', e);
            this.storage = null;
        }
    }

    private getNamespacedKey(key: string): string {
        return `${this.namespacePrefix}${key}`;
    }

    /**
     * Sets an item in local storage.
     * @param key The key for the item.
     * @param value The value to store. Can be any serializable type.
     * @param expiresInSeconds Optional. Time in seconds until the item expires.
     * @returns True if the item was set successfully, false otherwise.
     */
    set<T>(key: string, value: T, expiresInSeconds?: number): boolean {
        if (!this.storage) {
            console.warn(`LocalStorageService: Cannot set item '${key}', local storage is not available.`);
            return false;
        }

        const namespacedKey = this.getNamespacedKey(key);
        const wrapper: StorageItemWrapper<T> = { payload: value };

        if (expiresInSeconds && expiresInSeconds > 0) {
            wrapper.expiry = Date.now() + expiresInSeconds * 1000;
        }

        try {
            const serializedValue = JSON.stringify(wrapper);
            this.storage.setItem(namespacedKey, serializedValue);
            return true;
        } catch (e) {
            if (e instanceof DOMException && (e.name === 'QuotaExceededError' || e.code === 22)) {
                console.error(`LocalStorageService: Quota exceeded when trying to set item with key "${key}".`, e);
            } else {
                console.error(`LocalStorageService: Error setting item with key "${key}". Value not stringified or other error.`, e);
            }
            return false;
        }
    }

    /**
     * Retrieves an item from local storage.
     * @param key The key for the item.
     * @param defaultValue Optional. The value to return if the key is not found or the item is expired/invalid.
     * @returns The retrieved item, or the defaultValue/null if not found, expired, or an error occurred.
     */
    get<T>(key: string, defaultValue: T | null = null): T | null {
        if (!this.storage) {
            console.warn(`LocalStorageService: Cannot get item '${key}', local storage is not available.`);
            return defaultValue;
        }

        const namespacedKey = this.getNamespacedKey(key);
        try {
            const serializedValue = this.storage.getItem(namespacedKey);
            if (serializedValue === null) {
                return defaultValue;
            }

            const wrapper: StorageItemWrapper<T> = JSON.parse(serializedValue);

            if (wrapper.expiry && wrapper.expiry < Date.now()) {
                const originalKey = key; // The key before namespacing, as used by consumers
                console.log(`LocalStorageService: Item with key "${originalKey}" (namespaced: "${namespacedKey}") has expired. Removing and notifying.`);
                // Notify subscribers that this item has expired
                this.itemExpiredSubject.next(originalKey);
                // Then remove it
                this.remove(key); // Uses the public remove method which handles namespacing
                return defaultValue;
            }

            return wrapper.payload;
        } catch (e) {
            console.error(`LocalStorageService: Error getting or parsing item with key "${key}". Item might be corrupted. Removing.`, e);
            // Potentially corrupted data, remove it
            this.storage.removeItem(namespacedKey);
            return defaultValue;
        }
    }

    /**
     * Removes an item from local storage.
     * @param key The key for the item to remove.
     * @returns True if the item was removed successfully or did not exist, false if storage is unavailable or an error occurred.
     */
    remove(key: string): boolean {
        if (!this.storage) {
            console.warn(`LocalStorageService: Cannot remove item '${key}', local storage is not available.`);
            return false;
        }
        const namespacedKey = this.getNamespacedKey(key);
        try {
            this.storage.removeItem(namespacedKey);
            return true;
        } catch (e) {
            console.error(`LocalStorageService: Error removing item with key "${key}".`, e);
            return false;
        }
    }

    /**
     * Clears all items managed by this service instance (i.e., within its configured namespace).
     * @returns True if items were cleared successfully or no items to clear, false if storage is unavailable or an error occurred.
     */
    clearAll(): boolean {
        if (!this.storage) {
            console.warn('LocalStorageService: Cannot clear items, local storage is not available.');
            return false;
        }
        try {
            const keysToRemove: string[] = [];
            for (let i = 0; i < this.storage.length; i++) {
                const key = this.storage.key(i);
                if (key && key.startsWith(this.namespacePrefix)) {
                    keysToRemove.push(key);
                }
            }
            keysToRemove.forEach(key => this.storage!.removeItem(key)); // storage is checked non-null
            console.log(`LocalStorageService: Cleared ${keysToRemove.length} items for namespace "${this.currentNamespace}".`);
            return true;
        } catch (e) {
            console.error(`LocalStorageService: Error clearing items for namespace "${this.currentNamespace}".`, e);
            return false;
        }
    }

    /**
     * Clears all expired or corrupted items within the service's namespace.
     * This can be called periodically if needed (e.g., on application startup).
     * @returns True if the cleanup was attempted successfully, false if storage is unavailable or an error occurred.
     */
    clearExpiredItems(): boolean {
        if (!this.storage) {
            console.warn('LocalStorageService: Cannot clear expired items, local storage is not available.');
            return false;
        }
        try {
            let itemsScanned = 0;
            const keysToRemove: string[] = [];

            for (let i = 0; i < this.storage.length; i++) {
                const namespacedKey = this.storage.key(i);
                if (namespacedKey && namespacedKey.startsWith(this.namespacePrefix)) {
                    itemsScanned++;
                    try {
                        const serializedValue = this.storage.getItem(namespacedKey);
                        if (serializedValue) {
                            const wrapper: StorageItemWrapper<unknown> = JSON.parse(serializedValue);
                            if (wrapper.expiry && wrapper.expiry < Date.now()) {
                                if (!keysToRemove.includes(namespacedKey)) keysToRemove.push(namespacedKey);
                            }
                        } else {
                            // Key exists but no value, likely an anomaly, mark for removal
                            if (!keysToRemove.includes(namespacedKey)) keysToRemove.push(namespacedKey);
                        }
                    } catch (e) {
                        // Corrupted item or other parsing error
                        console.warn(`LocalStorageService: Error parsing item with key "${namespacedKey}" during expiry check. Marking for removal.`, e);
                        if (!keysToRemove.includes(namespacedKey)) keysToRemove.push(namespacedKey);
                    }
                }
            }

            keysToRemove.forEach(key => this.storage!.removeItem(key));

            if (keysToRemove.length > 0) {
                console.log(`LocalStorageService: Cleared ${keysToRemove.length} expired or corrupted items for namespace "${this.currentNamespace}". Scanned ${itemsScanned} namespaced items.`);
            }
            return true;
        } catch (e) {
            console.error(`LocalStorageService: Error during cleanup of expired items for namespace "${this.currentNamespace}".`, e);
            return false;
        }
    }
}
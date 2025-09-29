import { Injectable, inject } from '@angular/core';
import {
  Firestore,
  collection,
  addDoc,
  collectionData,
  doc,
  getDoc,
  updateDoc,
  deleteDoc,
  DocumentReference,
  CollectionReference,
  query,
  where,
  getDocs,
  setDoc,
  WhereFilterOp
} from '@angular/fire/firestore';
import { Observable } from 'rxjs';

/**
 * Base interface for Firestore documents handled by this service.
 * Ensures that documents are expected to have an `id` field,
 * which is typically added when retrieving data with `idField`.
 */
export interface FirestoreDocument {
  id?: string;          // Automatically added by the service on retrieval
}

/**
 * Provides generic methods for interacting with Firestore collections.
 * Handles common CRUD operations (Create, Read, Update, Delete) and querying.
 */
@Injectable({
  providedIn: 'root'
})
export class FirestoreDataService {
  /** Injected Firestore instance for database interactions. */
  private firestore: Firestore = inject(Firestore);

  /**
   * Adds a new document to the specified Firestore collection.
   * Automatically adds a `createdAt` timestamp to the document.
   * @template T The type of the data object being added (should extend Omit<object, 'id' | 'createdAt'>).
   * @param collectionName The name of the Firestore collection.
   * @param data The data object to add (without 'id' or 'createdAt').
   * @returns A Promise resolving with the DocumentReference of the newly created document.
   */
  addRecord<T extends Omit<object, 'id' | 'createdAt'>>(
    collectionName: string,
    data: T
  ): Promise<DocumentReference<T & { createdAt: string }>> {
    // Get a reference to the specified collection, strongly typed.
    const dataCollection = collection(this.firestore, collectionName) as CollectionReference<T & { createdAt: string }>;
    // Add the current timestamp to the data before saving.
    const dataWithTimestamp = { ...data, createdAt: new Date().toISOString() };
    // Add the document to the collection.
    return addDoc(dataCollection, dataWithTimestamp) as Promise<DocumentReference<T & { createdAt: string }>>;
  }

  /**
   * Creates or overwrites a document with a specific ID in the specified Firestore collection.
   * Automatically adds a `createdAt` timestamp to the document.
   * @template T The type of the document being set (should extend FirestoreDocument).
   * @param collectionName The name of the Firestore collection.
   * @param id The specific ID to use for the document.
   * @param data The data object to set (should match the structure of T, excluding 'id' and 'createdAt').
   * @returns A Promise resolving when the set operation is complete.
   */
  setRecordWithId<T extends FirestoreDocument>(
    collectionName: string,
    id: string,
    data: Omit<T, 'id'> // Input data excludes id and createdAt
  ): Promise<void> {
    // Type the DocumentReference based on the data structure *without* the id field,
    // as the id is part of the reference path, not the stored data itself.
    const docRef = doc(this.firestore, collectionName, id) as DocumentReference<Omit<T, 'id'>>;
    // Use setDoc to create or overwrite the document with the specified ID.
    return setDoc(docRef, data);
  }

  /**
   * Retrieves all documents from the specified Firestore collection as an Observable stream.
   * Automatically includes the document ID in each retrieved object under the 'id' field.
   * @template T The expected type of the documents in the collection (should extend FirestoreDocument).
   * @param collectionName The name of the Firestore collection.
   * @returns An Observable emitting an array of documents (T[]).
   */
  getRecords<T extends FirestoreDocument>(collectionName: string): Observable<T[]> {
    // Get a reference to the specified collection, strongly typed.
    const dataCollection = collection(this.firestore, collectionName) as CollectionReference<T>;
    // Use collectionData to get an observable stream of documents, mapping the ID to the 'id' field.
    return collectionData(dataCollection, { idField: 'id' }) as Observable<T[]>;
  }

  /**
   * Retrieves a single document by its ID from the specified Firestore collection.
   * @template T The expected type of the document (should extend FirestoreDocument).
   * @param collectionName The name of the Firestore collection.
   * @param id The unique ID of the document to retrieve.
   * @returns A Promise resolving with the document data (T) if found, otherwise undefined.
   */
  async getRecordById<T extends FirestoreDocument>(collectionName: string, id: string): Promise<T | undefined> {
    // Create a DocumentReference for the specific document.
    const docRef = doc(this.firestore, collectionName, id) as DocumentReference<T>;
    // Fetch the document snapshot.
    const docSnap = await getDoc(docRef);
    // Check if the document exists and return its data including the ID.
    if (docSnap.exists()) {
      return { id: docSnap.id, ...docSnap.data() } as T;
    } else {
      // Document not found.
      return undefined;
    }
  }

  /**
   * Updates an existing document in the specified Firestore collection.
   * Requires the document ID for identification.
   * @template T The type of the document being updated (should extend FirestoreDocument).
   * @param collectionName The name of the Firestore collection.
   * @param id The unique ID of the document to update. Must be provided.
   * @param data A partial object containing the fields to update.
   * @returns A Promise resolving when the update is complete, or rejecting if the ID is missing.
   */
  updateRecord<T extends FirestoreDocument>(
    collectionName: string,
    id: string,
    data: Partial<Omit<T, 'id'>> // Data is partial and excludes the 'id' field
  ): Promise<void> {
    // Ensure an ID is provided for the update operation.
    if (!id) {
      return Promise.reject(new Error("Document ID is required for update."));
    }
    // Create a DocumentReference for the specific document.
    const docRef = doc(this.firestore, collectionName, id) as DocumentReference<T>;
    // Perform the update operation. 'as any' is used here because updateDoc expects specific types,
    // but Partial<Omit<T, 'id'>> is a safe general type for updates.
    return updateDoc(docRef, data as any);
  }

  /**
   * Deletes a document from the specified Firestore collection by its ID.
   * Requires the document ID for identification.
   * @param collectionName The name of the Firestore collection.
   * @param id The unique ID of the document to delete. Must be provided.
   * @returns A Promise resolving when the deletion is complete, or rejecting if the ID is missing.
   */
  deleteRecord(collectionName: string, id: string): Promise<void> {
    // Ensure an ID is provided for the delete operation.
    if (!id) {
      return Promise.reject(new Error("Document ID is required for deletion."));
    }
    // Create a DocumentReference for the specific document.
    const docRef = doc(this.firestore, collectionName, id);
    // Perform the delete operation.
    return deleteDoc(docRef);
  }

  /**
   * Retrieves all documents from the specified Firestore collection *once*.
   * Uses getDocs for a Promise-based fetch.
   * Automatically includes the document ID in each retrieved object under the 'id' field.
   * @template T The expected type of the documents in the collection (should extend FirestoreDocument).
   * @param collectionName The name of the Firestore collection.
   * @returns A Promise resolving with an array of documents (T[]).
   */
  async getAllRecordsOnce<T extends FirestoreDocument>(collectionName: string): Promise<T[]> {
    // Get a reference to the collection, typed appropriately for reading data.
    // Note: Typing as CollectionReference<Omit<T, 'id'>> might be slightly more accurate
    // for the raw data before we add the id, but CollectionReference<T> often works fine.
    const dataCollection = collection(this.firestore, collectionName) as CollectionReference<T>;
    // Execute the query to get all documents.
    const querySnapshot = await getDocs(dataCollection);
    const results: T[] = [];
    // Process each document in the snapshot, adding the ID to the result object.
    querySnapshot.forEach((doc) => {
      // Ensure the data() exists before spreading
      const data = doc.data();
      if (data) {
        results.push({ id: doc.id, ...data } as T);
      }
    });
    return results;
  }

  /**
   * Queries documents in a collection based on a specific field, operator, and value.
   * @template T The expected type of the documents in the collection (should extend FirestoreDocument).
   * @param collectionName The name of the Firestore collection.
   * @param field The name of the field to query on (keyof T, excluding 'id').
   * @param operator The comparison operator (e.g., '==', '<', 'array-contains').
   * @param value The value to compare the field against.
   * @returns A Promise resolving with an array of documents (T[]) matching the query.
   */
  async queryRecords<T extends FirestoreDocument>(
    collectionName: string,
    field: keyof Omit<T, 'id'>, // Field name must be a key of T, excluding 'id'
    operator: WhereFilterOp,    // Firestore query operator
    value: any                  // Value to compare against
  ): Promise<T[]> {
    // Get a reference to the collection, typed without the 'id' for querying purposes.
    const dataCollection = collection(this.firestore, collectionName) as CollectionReference<Omit<T, 'id'>>;
    // Construct the Firestore query.
    const q = query(dataCollection, where(field as string, operator, value));
    // Execute the query.
    const querySnapshot = await getDocs(q);
    const results: T[] = [];
    // Process each document in the snapshot, adding the ID to the result object.
    querySnapshot.forEach((doc) => {
       // Ensure the data() exists before spreading
      const data = doc.data();
      if (data) {
        results.push({ id: doc.id, ...data } as T);
      }
    });
    return results;
  }
}

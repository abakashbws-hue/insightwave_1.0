import { environment } from '../../../environments/environment';

export class URLUtil {
    /**
     * Get the base URL without any path
     * @returns {string} Base URL (protocol + hostname + port)
     */
    static getBaseUrlWithoutPath(): string {
      // Use the URL constructor for robust URL parsing
      const currentUrl = window.location.href;
      const urlObject = new URL(currentUrl);
  
      // Construct base URL using origin property
      // Origin includes protocol, hostname, and port
      return urlObject.origin + '/chatbot';
    }
  
    /**
     * Get the base URL without any path
     * @returns {string} Base URL (protocol + hostname + port)
     */
    static getApiServerBaseUrl(): string {
        return environment.agentUrl || '';
    }
  
    static getWSServerUrl(): string {
      let url = this.getApiServerBaseUrl();
      // For adk web, when the api server is not set, use the current host
      if (!url || url == '') {
        return window.location.host;
      }
  
      // For local development, api server address is passed in runtime_config
      if (url.startsWith('http://')) {
        return url.slice('http://'.length);
      } else if (url.startsWith('https://')) {
        return url.slice('https://'.length);
      } else {
        return url;
      }
    }
  }
  